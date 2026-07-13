from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from zippictureviewer.folder_context import FolderContext
from zippictureviewer.models import ArchiveMemberId, ImageEntry
from zippictureviewer.session_store import SESSION_VERSION, SessionStore


def test_save_root_restores_an_empty_folder(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    session_path = tmp_path / "state" / "session.json"
    store = SessionStore(session_path)

    store.save_root(root)

    assert store.last_root() == root
    assert store.last_context() == FolderContext.from_path(root)
    data = _read_json(session_path)
    assert data["version"] == SESSION_VERSION
    assert data["positions"] == {}


def test_session_preserves_a_symlink_alias_as_the_logical_root(
    tmp_path: Path,
) -> None:
    real_root = tmp_path / "storage" / "collection"
    real_root.mkdir(parents=True)
    alias = tmp_path / "selected-alias"
    try:
        alias.symlink_to(real_root, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlinks are unavailable: {error}")
    context = FolderContext.from_path(alias)
    session_path = tmp_path / "session.json"
    store = SessionStore(session_path)

    store.save_root(context)

    restored = store.last_context()
    assert restored is not None
    assert restored.logical_path == alias
    assert restored.access_path == real_root.resolve()
    assert _read_json(session_path)["last_root"]["logical_path"] == str(alias)


def test_save_position_keeps_the_legacy_three_argument_api(tmp_path: Path) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    archive = root / "book.zip"
    archive.touch()
    entry = ImageEntry(archive, "page02.jpg")
    store = SessionStore(tmp_path / "session.json")

    store.save_position(root, entry, 8)

    assert store.restore_index(root, [entry]) == 0
    assert store.last_root() == root


def test_structured_member_id_restores_the_exact_duplicate_zip_record(
    tmp_path: Path,
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    archive = root / "duplicates.zip"
    archive.touch()
    first_duplicate = ImageEntry(
        archive,
        "page.jpg",
        member_id=ArchiveMemberId(record_index=0, header_offset=10, crc=101),
    )
    saved_duplicate = ImageEntry(
        archive,
        "page.jpg",
        member_id=ArchiveMemberId(record_index=1, header_offset=200, crc=202),
    )
    store = SessionStore(tmp_path / "session.json")

    store.save_position(
        root,
        saved_duplicate,
        1,
        [first_duplicate, saved_duplicate],
    )

    saved_member_id = _read_json(store.path)["positions"][str(root)]["member_id"]
    assert saved_member_id == {
        "record_index": 1,
        "header_offset": 200,
        "crc": 202,
    }
    assert store.restore_index(root, [saved_duplicate, first_duplicate]) == 0


def test_existing_version_2_string_member_id_matches_modern_entries(
    tmp_path: Path,
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    archive = root / "book.zip"
    archive.touch()
    context = FolderContext.from_path(root)
    session_path = tmp_path / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "version": SESSION_VERSION,
                "last_root": context.to_dict(),
                "positions": {
                    context.session_key: {
                        "container_id": "book.zip",
                        "member_id": "page2.jpg",
                        "container_index": 1,
                        "global_index": 1,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    entries = [
        ImageEntry(
            archive,
            "page1.jpg",
            member_id=ArchiveMemberId(0, 10, 101),
        ),
        ImageEntry(
            archive,
            "page2.jpg",
            member_id=ArchiveMemberId(1, 200, 202),
        ),
    ]

    assert SessionStore(session_path).restore_index(context, entries) == 1


def test_restore_prefers_nearest_item_in_the_same_container(
    tmp_path: Path,
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    archive_a = root / "a.zip"
    archive_b = root / "b.zip"
    archive_a.touch()
    archive_b.touch()
    original_entries = [
        ImageEntry(archive_b, "cover.jpg"),
        ImageEntry(archive_a, "page1.jpg"),
        ImageEntry(archive_a, "page2.jpg"),
        ImageEntry(archive_a, "page3.jpg"),
    ]
    store = SessionStore(tmp_path / "session.json")
    store.save_position(root, original_entries[2], 2, original_entries)

    entries_after_deletion = [
        ImageEntry(archive_b, "cover.jpg"),
        ImageEntry(archive_a, "page1.jpg"),
        ImageEntry(archive_a, "page3.jpg"),
    ]

    assert store.restore_index(root, entries_after_deletion) == 2


def test_restore_uses_global_first_when_saved_container_is_gone(
    tmp_path: Path,
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    old_archive = root / "old.zip"
    other_archive = root / "other.zip"
    old_archive.touch()
    other_archive.touch()
    original_entries = [
        ImageEntry(other_archive, "other1.jpg"),
        ImageEntry(old_archive, "old1.jpg"),
        ImageEntry(old_archive, "old2.jpg"),
    ]
    store = SessionStore(tmp_path / "session.json")
    store.save_position(root, original_entries[2], 2, original_entries)

    unrelated_entries = [
        ImageEntry(other_archive, "other1.jpg"),
        ImageEntry(other_archive, "other2.jpg"),
        ImageEntry(other_archive, "other3.jpg"),
    ]

    assert store.restore_index(root, unrelated_entries) == 0


def test_version_1_session_is_migrated_and_restored(tmp_path: Path) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    archive = root / "book.zip"
    archive.touch()
    session_path = tmp_path / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "last_root": str(root),
                "folders": {
                    str(root): {
                        "archive_path": str(archive),
                        "member_name": "page2.jpg",
                        "index": 7,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    store = SessionStore(session_path)
    entries = [
        ImageEntry(archive, "page1.jpg"),
        ImageEntry(archive, "page2.jpg"),
    ]

    assert store.last_root() == root
    assert store.restore_index(root, entries) == 1
    migrated = _read_json(session_path)
    assert migrated["version"] == SESSION_VERSION
    assert "folders" not in migrated
    assert migrated["last_root"]["logical_path"] == str(root)
    assert migrated["positions"][str(root)]["member_id"] == "page2.jpg"


def test_corrupt_session_is_ignored_and_replaced_on_save(tmp_path: Path) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    session_path = tmp_path / "session.json"
    session_path.write_text("{not-json", encoding="utf-8")
    store = SessionStore(session_path)

    assert store.last_root() is None

    store.save_root(root)

    assert store.last_root() == root
    assert _read_json(session_path)["version"] == SESSION_VERSION


def test_atomic_write_replaces_a_complete_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    session_path = tmp_path / "session.json"
    old_payload = json.dumps({"version": 2, "last_root": None, "positions": {}})
    session_path.write_text(old_payload, encoding="utf-8")
    store = SessionStore(session_path)
    real_replace = os.replace
    observations: list[tuple[Path, str, str]] = []

    def observe_replace(source: Path, destination: Path) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        observations.append(
            (
                source_path.parent,
                source_path.read_text(encoding="utf-8"),
                destination_path.read_text(encoding="utf-8"),
            )
        )
        real_replace(source, destination)

    monkeypatch.setattr("zippictureviewer.session_store.os.replace", observe_replace)

    store.save_root(root)

    assert len(observations) == 1
    temporary_parent, new_payload, observed_old_payload = observations[0]
    assert temporary_parent == session_path.parent
    assert json.loads(new_payload)["last_root"]["logical_path"] == str(root)
    assert observed_old_payload == old_payload
    assert _read_json(session_path)["last_root"]["logical_path"] == str(root)


def test_failed_atomic_replace_preserves_previous_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    session_path = tmp_path / "session.json"
    old_payload = json.dumps({"version": 2, "last_root": None, "positions": {}})
    session_path.write_text(old_payload, encoding="utf-8")
    store = SessionStore(session_path)

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("zippictureviewer.session_store.os.replace", fail_replace)

    store.save_root(root)

    assert session_path.read_text(encoding="utf-8") == old_payload
    assert list(session_path.parent.glob(f".{session_path.name}.*.tmp")) == []


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
