from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageEntry:
    archive_path: Path
    member_name: str

    @property
    def archive_label(self) -> str:
        return self.archive_path.name

    @property
    def image_label(self) -> str:
        return Path(self.member_name).name

    @property
    def is_animated(self) -> bool:
        return Path(self.member_name).suffix.lower() == ".gif"
