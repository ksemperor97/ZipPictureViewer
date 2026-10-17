from __future__ import annotations

import os
from pathlib import Path
from typing import Callable
from zipfile import BadZipFile, ZipInfo

from .archive_metadata import (
    ArchiveResourceLimitError,
    MetadataEncoding,
    ScanOptions,
    read_archive_infos,
)
from .formats import ARCHIVE_EXTENSIONS, IMAGE_EXTENSIONS
from .models import (
    ArchiveMemberId,
    ContainerRevision,
    ImageEntry,
    ScanIssue,
    ScanResult,
)
from .natural_sort import natural_sorted


CancelCheck = Callable[[], bool]
ProgressCallback = Callable[[Path, int], None]
PreviewCallback = Callable[[list[ImageEntry]], None]


def scan_image_index(
    root: Path,
    *,
    options: ScanOptions | None = None,
    generation: int = 0,
    cancel_check: CancelCheck | None = None,
    progress_callback: ProgressCallback | None = None,
    preview_callback: PreviewCallback | None = None,
) -> ScanResult:
    """Build an image index while isolating failures to each container.

    The priority container (``options.priority_container`` when it was
    discovered, otherwise the first container) is scanned first and handed
    to ``preview_callback`` so the UI can show it before the rest is read.
    """

    root = Path(root)
    options = options or ScanOptions()
    containers, issues, cancelled, discovered_files = _discover_containers(
        root,
        cancel_check,
    )
    result = ScanResult(
        issues=issues,
        cancelled=cancelled,
        generation=generation,
        discovered_files=discovered_files,
    )
    if cancelled or not containers:
        return result

    priority = (
        options.priority_container
        if options.priority_container in containers
        else containers[0]
    )
    try:
        early = _scan_container(priority, options, options.max_index_entries, cancel_check)
    except _ScanCancelled:
        result.cancelled = True
        return result
    if preview_callback is not None and isinstance(early, list) and early:
        preview_callback(early)

    for processed_count, container_path in enumerate(containers, start=1):
        if cancel_check is not None and cancel_check():
            result.cancelled = True
            break
        if container_path == priority:
            outcome = early
        else:
            reserved = len(early) if isinstance(early, list) else 0
            budget = options.max_index_entries - len(result.entries) - reserved
            try:
                outcome = _scan_container(container_path, options, budget, cancel_check)
            except _ScanCancelled:
                result.cancelled = True
                break
        if isinstance(outcome, ScanIssue):
            result.issues.append(outcome)
        else:
            result.entries.extend(outcome)

        if progress_callback is not None:
            progress_callback(container_path, processed_count)
        result.containers_scanned = processed_count

    return result


def _scan_container(
    container_path: Path,
    options: ScanOptions,
    max_entries: int,
    cancel_check: CancelCheck | None,
) -> list[ImageEntry] | ScanIssue:
    """Scan one container, turning its failure into an issue for that container."""

    if not _is_archive_path(container_path):
        try:
            return _scan_folder(container_path, max_entries=max_entries, cancel_check=cancel_check)
        except _ARCHIVE_ERRORS as exc:
            return _issue_for(container_path, "scan_folder", exc)
    try:
        return _scan_archive(
            container_path,
            options.encoding_for(container_path),
            max_members=options.max_archive_members,
            max_central_directory_bytes=options.max_central_directory_bytes,
            max_entries=max_entries,
            cancel_check=cancel_check,
        )
    except _ARCHIVE_ERRORS as exc:
        return _issue_for(container_path, "scan_archive", exc)


def _discover_containers(
    root: Path,
    cancel_check: CancelCheck | None = None,
) -> tuple[list[Path], list[ScanIssue], bool, int]:
    issues: list[ScanIssue] = []
    if not root.exists():
        error = FileNotFoundError(f"Root does not exist: {root}")
        return [], [_issue_for(root, "discover", error)], False, 0

    if root.is_file():
        return ([root] if _is_archive_path(root) else []), issues, False, 1
    if not root.is_dir():
        error = OSError(f"Root is not a directory or supported archive: {root}")
        return [], [_issue_for(root, "discover", error)], False, 0

    archives: list[Path] = []
    image_folders: list[Path] = []
    cancelled = False
    discovered_files = 0

    def collect_walk_error(error: OSError) -> None:
        target = Path(error.filename) if error.filename else root
        issues.append(_issue_for(target, "discover", error))

    for directory, _, filenames in os.walk(root, onerror=collect_walk_error):
        if cancel_check is not None and cancel_check():
            cancelled = True
            break

        directory_path = Path(directory)
        discovered_files += len(filenames)
        if any(_is_image_member(name) for name in filenames):
            image_folders.append(directory_path)
        archives.extend(
            directory_path / name
            for name in filenames
            if Path(name).suffix.casefold() in ARCHIVE_EXTENSIONS
        )

    containers = [*archives, *image_folders]
    containers = natural_sorted(containers, key=lambda path: path.relative_to(root))
    return containers, issues, cancelled, discovered_files


def _scan_archive(
    archive_path: Path,
    metadata_encoding: MetadataEncoding,
    *,
    max_members: int = 100_000,
    max_central_directory_bytes: int = 64 * 1024 * 1024,
    max_entries: int = 100_000,
    cancel_check: CancelCheck | None = None,
) -> list[ImageEntry]:
    if max_entries <= 0:
        raise ArchiveResourceLimitError("Image index entry limit has been reached.")
    revision = ContainerRevision.from_path(archive_path)
    infos = read_archive_infos(
        archive_path,
        metadata_encoding,
        max_members=max_members,
        max_central_directory_bytes=max_central_directory_bytes,
    )
    entries: list[ImageEntry] = []
    for record_index, info in enumerate(infos):
        if cancel_check is not None and record_index % 256 == 0 and cancel_check():
            raise _ScanCancelled
        if info.is_dir() or not _is_image_member(info.filename):
            continue
        if len(entries) >= max_entries:
            raise ArchiveResourceLimitError(
                f"Image index exceeds the {max_entries}-entry remaining budget."
            )
        entries.append(
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
                encryption=_archive_encryption(info),
            )
        )
    return natural_sorted(entries, key=lambda entry: entry.member_name)


def _scan_folder(
    folder_path: Path,
    *,
    max_entries: int = 100_000,
    cancel_check: CancelCheck | None = None,
) -> list[ImageEntry]:
    entries: list[ImageEntry] = []
    members: list[str] = []
    for index, path in enumerate(folder_path.iterdir()):
        if cancel_check is not None and index % 256 == 0 and cancel_check():
            raise _ScanCancelled
        if not path.is_file() or not _is_image_member(path.name):
            continue
        if len(members) >= max_entries:
            raise ArchiveResourceLimitError(
                f"Image index exceeds the {max_entries}-entry remaining budget."
            )
        members.append(path.name)
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
    if isinstance(error, ArchiveResourceLimitError):
        error_kind = "resource_limit"
        retryable = False
    elif isinstance(error, BadZipFile):
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


def _archive_encryption(info: ZipInfo) -> str | None:
    if not info.flag_bits & 0x1:
        return None
    if info.compress_type == 99 or _has_extra_field(info.extra, 0x9901):
        return "aes"
    return "zipcrypto"


def _has_extra_field(extra: bytes, field_id: int) -> bool:
    offset = 0
    while offset + 4 <= len(extra):
        current_id = int.from_bytes(extra[offset : offset + 2], "little")
        field_size = int.from_bytes(extra[offset + 2 : offset + 4], "little")
        if current_id == field_id:
            return True
        offset += 4 + field_size
    return False


_ARCHIVE_ERRORS = (
    ArchiveResourceLimitError,
    BadZipFile,
    EOFError,
    NotImplementedError,
    RuntimeError,
    UnicodeError,
    OSError,
)


class _ScanCancelled(Exception):
    pass
