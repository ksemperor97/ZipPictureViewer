from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class ContainerRevision:
    """A cheap source fingerprint used to reject stale index/cache entries."""

    path: Path
    mtime_ns: int
    size: int
    device: int = 0
    inode: int = 0
    ctime_ns: int = 0

    @classmethod
    def from_path(cls, path: Path) -> ContainerRevision:
        source_path = Path(path)
        stat_result = source_path.stat()
        return cls(
            path=source_path,
            mtime_ns=stat_result.st_mtime_ns,
            size=stat_result.st_size,
            device=stat_result.st_dev,
            inode=stat_result.st_ino,
            ctime_ns=stat_result.st_ctime_ns,
        )


@dataclass(frozen=True)
class ArchiveMemberId:
    """Identity for one central-directory record, including duplicate names."""

    record_index: int
    header_offset: int
    crc: int


@dataclass(frozen=True)
class ImageEntry:
    archive_path: Path
    member_name: str
    source_kind: Literal["archive", "folder"]
    member_id: ArchiveMemberId | None = None
    source_revision: ContainerRevision | None = None
    encryption: Literal["zipcrypto", "aes"] | None = None

    @property
    def archive_label(self) -> str:
        return self.archive_path.name

    @property
    def image_label(self) -> str:
        return Path(self.member_name).name

    @property
    def is_animated(self) -> bool:
        return Path(self.member_name).suffix.lower() == ".gif"

    @property
    def source_path(self) -> Path:
        """Return the file whose revision controls this entry's contents."""

        if not self.is_archive_member:
            return self.archive_path / self.member_name
        return self.archive_path

    @property
    def is_archive_member(self) -> bool:
        return self.source_kind == "archive"


@dataclass(frozen=True)
class ScanIssue:
    target_path: Path
    stage: str
    error_kind: str
    message: str
    retryable: bool = False


@dataclass
class ScanResult:
    entries: list[ImageEntry] = field(default_factory=list)
    issues: list[ScanIssue] = field(default_factory=list)
    cancelled: bool = False
    generation: int = 0
    discovered_files: int = 0
    containers_scanned: int = 0
