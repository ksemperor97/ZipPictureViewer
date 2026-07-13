from __future__ import annotations

import os
from pathlib import Path
from typing import Callable
from zipfile import BadZipFile

from .archive_metadata import (
    MetadataEncoding,
    ScanOptions,
    read_archive_infos,
    validate_metadata_encoding,
)
from .models import (
    ArchiveMemberId,
    ContainerRevision,
    ImageEntry,
    ScanIssue,
    ScanResult,
)
from .natural_sort import natural_sorted


ARCHIVE_EXTENSIONS = {".cbz", ".zip"}
IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
CancelCheck = Callable[[], bool]
ProgressCallback = Callable[[Path, int], None]


def find_archives(root: Path) -> list[Path]:
    containers, _, _ = _discover_containers(Path(root))
    return [path for path in containers if _is_archive_path(path)]


def find_image_folders(root: Path) -> list[Path]:
    containers, _, _ = _discover_containers(Path(root))
    return [path for path in containers if not _is_archive_path(path)]


def find_image_containers(root: Path) -> list[Path]:
    containers, _, _ = _discover_containers(Path(root))
    return containers


def image_members_in_archive(
    archive_path: Path,
    *,
    metadata_encoding: MetadataEncoding = "auto",
) -> list[str]:
    """Return display names for compatibility with the original API.

    Call :func:`scan_image_index` when exact duplicate-member identity or
    structured error details are required.
    """

    validate_metadata_encoding(metadata_encoding)
    try:
        entries = _scan_archive(Path(archive_path), metadata_encoding)
    except _ARCHIVE_ERRORS:
        return []
    return [entry.member_name for entry in entries]


def image_members_in_folder(folder_path: Path) -> list[str]:
    try:
        members = [
            path.name
            for path in Path(folder_path).iterdir()
            if path.is_file() and _is_image_member(path.name)
        ]
    except OSError:
        return []
    return natural_sorted(members)


def scan_image_index(
    root: Path,
    *,
    options: ScanOptions | None = None,
    generation: int = 0,
    cancel_check: CancelCheck | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ScanResult:
    """Build an image index while isolating failures to each container."""

    root = Path(root)
    options = options or ScanOptions()
    containers, issues, cancelled = _discover_containers(root, cancel_check)
    result = ScanResult(issues=issues, cancelled=cancelled, generation=generation)
    if cancelled:
        return result

    for processed_count, container_path in enumerate(containers, start=1):
        if cancel_check is not None and cancel_check():
            result.cancelled = True
            break

        stage = "scan_archive" if _is_archive_path(container_path) else "scan_folder"
        try:
            if _is_archive_path(container_path):
                encoding = options.encoding_for(container_path)
                entries = _scan_archive(container_path, encoding)
            else:
                entries = _scan_folder(container_path)
        except _ARCHIVE_ERRORS as exc:
            result.issues.append(_issue_for(container_path, stage, exc))
        else:
            result.entries.extend(entries)

        if progress_callback is not None:
            progress_callback(container_path, processed_count)

    return result


def build_image_index(root: Path) -> list[ImageEntry]:
    """Compatibility wrapper returning only successfully indexed entries."""

    return scan_image_index(root).entries


def _discover_containers(
    root: Path,
    cancel_check: CancelCheck | None = None,
) -> tuple[list[Path], list[ScanIssue], bool]:
    issues: list[ScanIssue] = []
    if not root.exists():
        error = FileNotFoundError(f"Root does not exist: {root}")
        return [], [_issue_for(root, "discover", error)], False

    if root.is_file():
        return ([root] if _is_archive_path(root) else []), issues, False
    if not root.is_dir():
        error = OSError(f"Root is not a directory or supported archive: {root}")
        return [], [_issue_for(root, "discover", error)], False

    archives: list[Path] = []
    image_folders: list[Path] = []
    cancelled = False

    def collect_walk_error(error: OSError) -> None:
        target = Path(error.filename) if error.filename else root
        issues.append(_issue_for(target, "discover", error))

    for directory, _, filenames in os.walk(root, onerror=collect_walk_error):
        if cancel_check is not None and cancel_check():
            cancelled = True
            break

        directory_path = Path(directory)
        if any(_is_image_member(name) for name in filenames):
            image_folders.append(directory_path)
        archives.extend(
            directory_path / name
            for name in filenames
            if Path(name).suffix.casefold() in ARCHIVE_EXTENSIONS
        )

    containers = [*archives, *image_folders]
    containers = natural_sorted(containers, key=lambda path: path.relative_to(root))
    return containers, issues, cancelled


def _scan_archive(
    archive_path: Path,
    metadata_encoding: MetadataEncoding,
) -> list[ImageEntry]:
    revision = ContainerRevision.from_path(archive_path)
    infos = read_archive_infos(archive_path, metadata_encoding)
    entries = [
        ImageEntry(
            archive_path=archive_path,
            member_name=info.filename,
            member_id=ArchiveMemberId(
                record_index=record_index,
                header_offset=info.header_offset,
                crc=info.CRC,
            ),
            source_revision=revision,
            source_kind="archive",
        )
        for record_index, info in enumerate(infos)
        if not info.is_dir() and _is_image_member(info.filename)
    ]
    return natural_sorted(entries, key=lambda entry: entry.member_name)


def _scan_folder(folder_path: Path) -> list[ImageEntry]:
    entries: list[ImageEntry] = []
    members = [
        path.name
        for path in folder_path.iterdir()
        if path.is_file() and _is_image_member(path.name)
    ]
    for member_name in natural_sorted(members):
        image_path = folder_path / member_name
        try:
            revision = ContainerRevision.from_path(image_path)
        except OSError:
            # Keep a transiently unreadable/disappeared file navigable. The
            # loader will surface its concrete error without hiding siblings.
            revision = None
        entries.append(
            ImageEntry(
                archive_path=folder_path,
                member_name=member_name,
                source_revision=revision,
                source_kind="folder",
            )
        )
    return entries


def _issue_for(target_path: Path, stage: str, error: BaseException) -> ScanIssue:
    if isinstance(error, BadZipFile):
        error_kind = "bad_zip"
        retryable = False
    elif isinstance(error, PermissionError):
        error_kind = "permission_denied"
        retryable = True
    elif isinstance(error, FileNotFoundError):
        error_kind = "not_found"
        retryable = True
    elif isinstance(error, NotImplementedError):
        error_kind = "unsupported_archive"
        retryable = False
    elif isinstance(error, UnicodeError):
        error_kind = "metadata_encoding"
        retryable = False
    elif isinstance(error, RuntimeError):
        error_kind = "archive_runtime"
        retryable = False
    else:
        error_kind = "os_error"
        retryable = True

    message = str(error).strip() or error.__class__.__name__
    return ScanIssue(
        target_path=Path(target_path),
        stage=stage,
        error_kind=error_kind,
        message=message,
        retryable=retryable,
    )


def _is_archive_path(path: Path) -> bool:
    return not path.is_dir() and path.suffix.casefold() in ARCHIVE_EXTENSIONS


def _is_image_member(member_name: str) -> bool:
    path = Path(member_name)
    if any(part.startswith("__MACOSX") for part in path.parts):
        return False
    if path.name.startswith("."):
        return False
    return path.suffix.casefold() in IMAGE_EXTENSIONS


_ARCHIVE_ERRORS = (
    BadZipFile,
    EOFError,
    NotImplementedError,
    RuntimeError,
    UnicodeError,
    OSError,
)
