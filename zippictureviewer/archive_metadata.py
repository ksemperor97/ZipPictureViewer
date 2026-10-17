from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping
from zipfile import ZipFile, ZipInfo


METADATA_ENCODINGS = {"auto", "cp437", "cp949"}
MetadataEncoding = Literal["auto", "cp437", "cp949"]
MEBIBYTE = 1024 * 1024
DEFAULT_MAX_ARCHIVE_MEMBERS = 100_000
DEFAULT_MAX_CENTRAL_DIRECTORY_BYTES = 64 * MEBIBYTE


class ArchiveResourceLimitError(ValueError):
    """Raised before a ZIP index can consume an unbounded resource budget."""


@dataclass(frozen=True)
class ScanOptions:
    """Archive-name policy with optional per-archive overrides.

    ``auto`` only selects CP949 when the original CP437-decoded name can be
    losslessly re-decoded to a plausible Hangul name. An explicit CP437 or
    CP949 override always wins.
    """

    metadata_encoding: MetadataEncoding = "auto"
    encoding_overrides: Mapping[Path, MetadataEncoding] = field(
        default_factory=dict
    )
    max_archive_members: int = DEFAULT_MAX_ARCHIVE_MEMBERS
    max_central_directory_bytes: int = DEFAULT_MAX_CENTRAL_DIRECTORY_BYTES
    max_index_entries: int = DEFAULT_MAX_ARCHIVE_MEMBERS
    # Container to scan and preview first (absolute, as discovered).
    priority_container: Path | None = None

    def __post_init__(self) -> None:
        validate_metadata_encoding(self.metadata_encoding)
        for encoding in self.encoding_overrides.values():
            validate_metadata_encoding(encoding)
        if min(
            self.max_archive_members,
            self.max_central_directory_bytes,
            self.max_index_entries,
        ) <= 0:
            raise ValueError("Scan resource limits must be positive")

    def encoding_for(self, archive_path: Path) -> MetadataEncoding:
        return self.encoding_overrides.get(archive_path, self.metadata_encoding)


def read_archive_infos(
    archive_path: Path,
    metadata_encoding: MetadataEncoding,
    *,
    max_members: int = DEFAULT_MAX_ARCHIVE_MEMBERS,
    max_central_directory_bytes: int = DEFAULT_MAX_CENTRAL_DIRECTORY_BYTES,
) -> list[ZipInfo]:
    validate_metadata_encoding(metadata_encoding)
    _validate_central_directory(
        archive_path,
        max_members=max_members,
        max_bytes=max_central_directory_bytes,
    )
    with ZipFile(archive_path) as archive:
        default_infos = archive.infolist()
    if len(default_infos) > max_members:
        raise ArchiveResourceLimitError(
            f"Archive contains {len(default_infos)} members; limit is {max_members}. "
            "Split the archive into smaller volumes before retrying."
        )
    use_cp949 = metadata_encoding == "cp949" or (
        metadata_encoding == "auto" and _archive_looks_cp949(default_infos)
    )
    if not use_cp949:
        return default_infos

    for info in default_infos:
        if info.flag_bits & 0x800 or info.filename.isascii():
            continue
        raw_name = info.filename.encode("cp437")
        info.filename = raw_name.decode("cp949")
    return default_infos


def validate_metadata_encoding(encoding: str) -> None:
    if encoding not in METADATA_ENCODINGS:
        choices = ", ".join(sorted(METADATA_ENCODINGS))
        raise ValueError(f"metadata_encoding must be one of: {choices}")


def _validate_central_directory(
    archive_path: Path,
    *,
    max_members: int,
    max_bytes: int,
) -> None:
    entry_count, directory_bytes = _central_directory_summary(archive_path)
    if entry_count is not None and entry_count > max_members:
        raise ArchiveResourceLimitError(
            f"Archive contains {entry_count} members; limit is {max_members}. "
            "Split the archive into smaller volumes before retrying."
        )
    if directory_bytes is not None and directory_bytes > max_bytes:
        raise ArchiveResourceLimitError(
            f"Archive central directory is {directory_bytes} bytes; "
            f"limit is {max_bytes} bytes. Split the archive before retrying."
        )


def _central_directory_summary(archive_path: Path) -> tuple[int | None, int | None]:
    file_size = archive_path.stat().st_size
    tail_size = min(file_size, 65_557)
    with archive_path.open("rb") as stream:
        stream.seek(file_size - tail_size)
        tail = stream.read(tail_size)
        eocd_offset = _find_eocd_offset(tail)
        if eocd_offset is None:
            return None, None
        fields = struct.unpack_from("<4s4H2LH", tail, eocd_offset)
        entry_count = fields[4]
        directory_bytes = fields[5]
        if entry_count != 0xFFFF and directory_bytes != 0xFFFFFFFF:
            return entry_count, directory_bytes

        absolute_eocd = file_size - tail_size + eocd_offset
        locator_offset = absolute_eocd - 20
        if locator_offset < 0:
            return None, None
        stream.seek(locator_offset)
        locator = stream.read(20)
        if len(locator) != 20 or locator[:4] != b"PK\x06\x07":
            return None, None
        zip64_eocd_offset = struct.unpack_from("<Q", locator, 8)[0]
        stream.seek(zip64_eocd_offset)
        record = stream.read(56)
        if len(record) < 56 or record[:4] != b"PK\x06\x06":
            return None, None
        zip64_fields = struct.unpack("<4sQ2H2L4Q", record)
        return zip64_fields[7], zip64_fields[8]


def _find_eocd_offset(tail: bytes) -> int | None:
    search_end = len(tail)
    while search_end > 0:
        offset = tail.rfind(b"PK\x05\x06", 0, search_end)
        if offset < 0:
            return None
        if len(tail) - offset >= 22:
            comment_length = struct.unpack_from("<H", tail, offset + 20)[0]
            if offset + 22 + comment_length == len(tail):
                return offset
        search_end = offset
    return None


def _archive_looks_cp949(infos: list[ZipInfo]) -> bool:
    legacy_infos = [
        info
        for info in infos
        if not info.filename.isascii() and not info.flag_bits & 0x800
    ]
    return bool(legacy_infos) and all(
        _cp949_candidate(info) is not None for info in legacy_infos
    )


def _cp949_candidate(info: ZipInfo) -> str | None:
    if info.flag_bits & 0x800 or info.filename.isascii():
        return None
    try:
        raw_name = info.filename.encode("cp437")
        candidate = raw_name.decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None

    has_hangul = any("\uac00" <= character <= "\ud7a3" for character in candidate)
    has_control = any(ord(character) < 32 for character in candidate)
    if not has_hangul or has_control:
        return None
    return candidate

