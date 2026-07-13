from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping
from zipfile import ZipFile, ZipInfo


METADATA_ENCODINGS = {"auto", "cp437", "cp949"}
MetadataEncoding = Literal["auto", "cp437", "cp949"]


@dataclass(frozen=True)
class ScanOptions:
    """Archive-name policy with optional per-archive overrides.

    ``auto`` only selects CP949 when the original CP437-decoded name can be
    losslessly re-decoded to a plausible Hangul name. An explicit CP437 or
    CP949 override always wins.
    """

    metadata_encoding: MetadataEncoding = "auto"
    encoding_overrides: Mapping[Path | str, MetadataEncoding] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        validate_metadata_encoding(self.metadata_encoding)
        for encoding in self.encoding_overrides.values():
            validate_metadata_encoding(encoding)

    def encoding_for(self, archive_path: Path) -> MetadataEncoding:
        target = _absolute_path(archive_path)
        for path, encoding in self.encoding_overrides.items():
            if _absolute_path(Path(path)) == target:
                return encoding
        return self.metadata_encoding


def read_archive_infos(
    archive_path: Path,
    metadata_encoding: MetadataEncoding,
) -> list[ZipInfo]:
    validate_metadata_encoding(metadata_encoding)
    with ZipFile(archive_path) as archive:
        default_infos = archive.infolist()
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


def _absolute_path(path: Path) -> Path:
    return path.expanduser().absolute()
