from __future__ import annotations

import warnings
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import zippictureviewer.archive_scanner as archive_scanner
from zippictureviewer.archive_scanner import ScanOptions, build_image_index, scan_image_index
from zippictureviewer.image_loader import read_image_bytes


def _write_archive(path: Path, members: list[tuple[str, bytes]]) -> None:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, contents in members:
            archive.writestr(name, contents)


def test_scan_isolates_bad_and_unreadable_archives(
    tmp_path: Path,
    monkeypatch,
) -> None:
    good_path = tmp_path / "1-good.zip"
    bad_path = tmp_path / "2-bad.zip"
    unreadable_path = tmp_path / "3-unreadable.zip"
    _write_archive(good_path, [("page.jpg", b"good")])
    bad_path.write_bytes(b"not a zip")
    _write_archive(unreadable_path, [("hidden.jpg", b"hidden")])

    original_read_infos = archive_scanner.read_archive_infos

    def deny_one_archive(path: Path, metadata_encoding: str):
        if path == unreadable_path:
            raise PermissionError(13, "Permission denied", str(path))
        return original_read_infos(path, metadata_encoding)

    monkeypatch.setattr(archive_scanner, "read_archive_infos", deny_one_archive)

    result = scan_image_index(tmp_path)

    assert [entry.member_name for entry in result.entries] == ["page.jpg"]
    assert {(issue.target_path, issue.error_kind) for issue in result.issues} == {
        (bad_path, "bad_zip"),
        (unreadable_path, "permission_denied"),
    }
    assert build_image_index(tmp_path) == result.entries


def test_duplicate_member_names_keep_exact_record_identity(tmp_path: Path) -> None:
    archive_path = tmp_path / "duplicates.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        _write_archive(
            archive_path,
            [("same.jpg", b"first"), ("same.jpg", b"second")],
        )

    entries = scan_image_index(tmp_path).entries

    assert [entry.member_name for entry in entries] == ["same.jpg", "same.jpg"]
    assert entries[0].member_id != entries[1].member_id
    assert [read_image_bytes(entry) for entry in entries] == [b"first", b"second"]


def test_single_archive_path_is_a_supported_scan_root(tmp_path: Path) -> None:
    archive_path = tmp_path / "book.cbz"
    _write_archive(archive_path, [("2.jpg", b"two"), ("1.jpg", b"one")])
    _write_archive(tmp_path / "ignored.zip", [("other.jpg", b"other")])

    result = scan_image_index(archive_path)

    assert [entry.member_name for entry in result.entries] == ["1.jpg", "2.jpg"]
    assert all(entry.archive_path == archive_path for entry in result.entries)


def test_one_folder_member_stat_failure_does_not_drop_its_siblings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    good_path = tmp_path / "1-good.jpg"
    unreadable_path = tmp_path / "2-unreadable.jpg"
    good_path.write_bytes(b"good")
    unreadable_path.write_bytes(b"unreadable")
    original_from_path = archive_scanner.ContainerRevision.from_path

    def fail_one_stat(path: Path):
        if path == unreadable_path:
            raise PermissionError(13, "Permission denied", str(path))
        return original_from_path(path)

    monkeypatch.setattr(
        archive_scanner.ContainerRevision,
        "from_path",
        staticmethod(fail_one_stat),
    )

    result = scan_image_index(tmp_path)

    assert [entry.member_name for entry in result.entries] == [
        "1-good.jpg",
        "2-unreadable.jpg",
    ]
    assert result.entries[0].source_revision is not None
    assert result.entries[1].source_revision is None


def test_cp949_names_are_auto_detected_and_can_be_overridden(tmp_path: Path) -> None:
    archive_path = tmp_path / "legacy.zip"
    _write_archive(
        archive_path,
        [("aa10.jpg", b"ten"), ("aa2.jpg", b"two")],
    )
    archive_bytes = archive_path.read_bytes()
    replacements = {
        b"aa10.jpg": "가10.jpg".encode("cp949"),
        b"aa2.jpg": "가2.jpg".encode("cp949"),
    }
    for placeholder, encoded_name in replacements.items():
        assert len(placeholder) == len(encoded_name)
        assert archive_bytes.count(placeholder) == 2
        archive_bytes = archive_bytes.replace(placeholder, encoded_name)
    archive_path.write_bytes(archive_bytes)

    auto_entries = scan_image_index(tmp_path).entries
    cp437_entries = scan_image_index(
        tmp_path,
        options=ScanOptions(encoding_overrides={archive_path: "cp437"}),
    ).entries

    assert [entry.member_name for entry in auto_entries] == ["가2.jpg", "가10.jpg"]
    assert all("가" not in entry.member_name for entry in cp437_entries)
    assert [read_image_bytes(entry) for entry in auto_entries] == [b"two", b"ten"]


def test_scan_reports_generation_progress_and_cancellation(tmp_path: Path) -> None:
    _write_archive(tmp_path / "1.zip", [("1.jpg", b"one")])
    _write_archive(tmp_path / "2.zip", [("2.jpg", b"two")])
    progress: list[tuple[Path, int]] = []

    result = scan_image_index(
        tmp_path,
        generation=42,
        progress_callback=lambda path, count: progress.append((path, count)),
    )
    cancelled = scan_image_index(
        tmp_path,
        generation=43,
        cancel_check=lambda: True,
    )

    assert result.generation == 42
    assert [count for _, count in progress] == [1, 2]
    assert cancelled.generation == 43
    assert cancelled.cancelled is True
    assert cancelled.entries == []


def test_scan_result_distinguishes_empty_and_unsupported_roots(
    tmp_path: Path,
) -> None:
    empty_result = scan_image_index(tmp_path)
    (tmp_path / "notes.txt").write_text("not an image", encoding="utf-8")
    unsupported_result = scan_image_index(tmp_path)

    assert empty_result.discovered_files == 0
    assert unsupported_result.discovered_files == 1
    assert unsupported_result.containers_scanned == 0
    assert unsupported_result.entries == []
