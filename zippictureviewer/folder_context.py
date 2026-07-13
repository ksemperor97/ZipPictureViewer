from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


SourceKind = Literal["folder", "archive"]
ARCHIVE_EXTENSIONS = frozenset({".cbz", ".zip"})


@dataclass(frozen=True)
class FolderContext:
    """A user-selected source and the path used to access its contents.

    ``logical_path`` deliberately keeps symbolic-link components. It is the
    stable identity used by session storage and sibling navigation.
    ``access_path`` is resolved separately and is used only for file access.
    """

    logical_path: Path
    access_path: Path
    source_kind: SourceKind

    def __post_init__(self) -> None:
        if self.source_kind not in ("folder", "archive"):
            raise ValueError(f"Unsupported source kind: {self.source_kind!r}")

        object.__setattr__(
            self,
            "logical_path",
            _absolute_without_resolving(Path(self.logical_path)),
        )
        object.__setattr__(
            self,
            "access_path",
            _resolve_for_access(_absolute_without_resolving(Path(self.access_path))),
        )

    @classmethod
    def from_path(
        cls,
        path: Path,
        source_kind: SourceKind | None = None,
    ) -> FolderContext:
        logical_path = _absolute_without_resolving(path)
        access_path = _resolve_for_access(logical_path)
        return cls(
            logical_path=logical_path,
            access_path=access_path,
            source_kind=source_kind or _infer_source_kind(logical_path, access_path),
        )

    @classmethod
    def from_dict(cls, value: object) -> FolderContext | None:
        if not isinstance(value, dict):
            return None

        logical_path = value.get("logical_path")
        access_path = value.get("access_path")
        source_kind = value.get("source_kind")
        if not isinstance(logical_path, str):
            return None
        if not isinstance(source_kind, str) or source_kind not in ("folder", "archive"):
            return None

        logical = _absolute_without_resolving(Path(logical_path))
        access = (
            _absolute_without_resolving(Path(access_path))
            if isinstance(access_path, str)
            else _resolve_for_access(logical)
        )
        return cls(logical, access, source_kind)

    @property
    def session_key(self) -> str:
        return str(self.logical_path)

    @property
    def is_accessible(self) -> bool:
        if self.source_kind == "archive":
            return self.access_path.is_file()
        return self.access_path.is_dir()

    def to_dict(self) -> dict[str, str]:
        return {
            "logical_path": str(self.logical_path),
            "access_path": str(self.access_path),
            "source_kind": self.source_kind,
        }


def coerce_folder_context(value: Path | FolderContext) -> FolderContext:
    if isinstance(value, FolderContext):
        return value
    return FolderContext.from_path(Path(value))


def _absolute_without_resolving(path: Path) -> Path:
    expanded = path.expanduser()
    return Path(os.path.abspath(os.fspath(expanded)))


def _resolve_for_access(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except (OSError, RuntimeError):
        return path


def _infer_source_kind(logical_path: Path, access_path: Path) -> SourceKind:
    has_archive_extension = (
        logical_path.suffix.casefold() in ARCHIVE_EXTENSIONS
        or access_path.suffix.casefold() in ARCHIVE_EXTENSIONS
    )
    if has_archive_extension and not access_path.is_dir():
        return "archive"
    return "folder"
