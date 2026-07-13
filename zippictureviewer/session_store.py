from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .folder_context import FolderContext, coerce_folder_context
from .models import ImageEntry


SESSION_VERSION = 2


def app_support_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ZipPictureViewer"

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "ZipPictureViewer"
        return Path.home() / "AppData" / "Roaming" / "ZipPictureViewer"

    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "ZipPictureViewer"
    return Path.home() / ".config" / "ZipPictureViewer"


APP_SUPPORT_DIR = app_support_dir()
SESSION_FILE = APP_SUPPORT_DIR / "session.json"


@dataclass(frozen=True)
class SavedPosition:
    container_id: str
    member_id: str
    container_index: int | None
    global_index: int

    def to_dict(self) -> dict[str, str | int]:
        value: dict[str, str | int] = {
            "container_id": self.container_id,
            "member_id": self.member_id,
            "global_index": self.global_index,
        }
        if self.container_index is not None:
            value["container_index"] = self.container_index
        return value


class SessionStore:
    def __init__(self, path: Path = SESSION_FILE) -> None:
        self.path = path

    def last_context(self) -> FolderContext | None:
        context = FolderContext.from_dict(self._read().get("last_root"))
        if context is None or not context.is_accessible:
            return None
        return context

    def last_root(self) -> Path | None:
        """Return the last logical path (the version 1 compatible API)."""

        context = self.last_context()
        return context.logical_path if context is not None else None

    def save_root(self, root: Path | FolderContext) -> None:
        """Persist a successfully opened root, including an empty root."""

        context = coerce_folder_context(root)
        data = self._read()
        data["version"] = SESSION_VERSION
        data["last_root"] = context.to_dict()
        if not isinstance(data.get("positions"), dict):
            data["positions"] = {}
        self._write(data)

    def save_position(
        self,
        root: Path | FolderContext,
        entry: ImageEntry,
        index: int,
        entries: Sequence[ImageEntry] | None = None,
        *,
        container_index: int | None = None,
    ) -> None:
        """Save a position while retaining the original three-argument API.

        Passing ``entries`` lets the store record an exact per-container index,
        which enables a nearest-item fallback if the saved member is deleted.
        """

        context = coerce_folder_context(root)
        resolved_container_index = self._container_index(
            context,
            entry,
            index,
            entries,
            container_index,
        )
        position = SavedPosition(
            container_id=self._container_id(context, entry.archive_path),
            member_id=entry.member_name,
            container_index=resolved_container_index,
            global_index=max(index, 0),
        )

        data = self._read()
        positions = data.setdefault("positions", {})
        if not isinstance(positions, dict):
            positions = {}
            data["positions"] = positions

        data["version"] = SESSION_VERSION
        data["last_root"] = context.to_dict()
        positions[context.session_key] = position.to_dict()
        self._write(data)

    def restore_index(
        self,
        root: Path | FolderContext,
        entries: list[ImageEntry],
    ) -> int:
        if not entries:
            return 0

        context = coerce_folder_context(root)
        positions = self._read().get("positions")
        if not isinstance(positions, dict):
            return 0

        raw_position = positions.get(context.session_key)
        if not isinstance(raw_position, dict):
            return 0

        restored = self._find_saved_entry(context, raw_position, entries)
        return restored if restored is not None else 0

    def _find_saved_entry(
        self,
        context: FolderContext,
        raw_position: dict[str, Any],
        entries: list[ImageEntry],
    ) -> int | None:
        container_id = raw_position.get("container_id")
        member_id = raw_position.get("member_id")
        if not isinstance(container_id, str) or not isinstance(member_id, str):
            return None

        matching_container: list[int] = []
        for index, entry in enumerate(entries):
            if self._container_id(context, entry.archive_path) != container_id:
                continue
            matching_container.append(index)
            if entry.member_name == member_id:
                return index

        if not matching_container:
            return None

        container_index = raw_position.get("container_index")
        if isinstance(container_index, int) and not isinstance(container_index, bool):
            nearest_index = min(max(container_index, 0), len(matching_container) - 1)
            return matching_container[nearest_index]

        return matching_container[0]

    def _container_index(
        self,
        context: FolderContext,
        entry: ImageEntry,
        global_index: int,
        entries: Sequence[ImageEntry] | None,
        explicit_index: int | None,
    ) -> int | None:
        if isinstance(explicit_index, int) and not isinstance(explicit_index, bool):
            return max(explicit_index, 0)
        if entries is None:
            return max(global_index, 0) if context.source_kind == "archive" else None

        target_container = self._container_id(context, entry.archive_path)
        if 0 <= global_index < len(entries):
            indexed_entry = entries[global_index]
            if (
                indexed_entry == entry
                and self._container_id(context, indexed_entry.archive_path)
                == target_container
            ):
                return sum(
                    self._container_id(context, candidate.archive_path)
                    == target_container
                    for candidate in entries[:global_index]
                )

        container_offset = 0
        for candidate in entries:
            if self._container_id(context, candidate.archive_path) != target_container:
                continue
            if candidate == entry:
                return container_offset
            container_offset += 1
        return None

    def _container_id(self, context: FolderContext, archive_path: Path) -> str:
        archive_access_path = _resolve_for_identity(archive_path)
        root_access_path = _resolve_for_identity(context.access_path)

        if context.source_kind == "archive" and archive_access_path == root_access_path:
            return "."

        try:
            relative_path = archive_access_path.relative_to(root_access_path)
        except ValueError:
            return str(archive_access_path)
        return relative_path.as_posix() or "."

    def _read(self) -> dict[str, Any]:
        raw_data = self._read_file()
        if raw_data.get("version") == SESSION_VERSION:
            return _normalized_v2(raw_data)
        if not _looks_like_v1(raw_data):
            return _empty_session()

        migrated = self._migrate_v1(raw_data)
        self._write(migrated)
        return migrated

    def _read_file(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _migrate_v1(self, data: dict[str, Any]) -> dict[str, Any]:
        migrated = _empty_session()

        raw_last_root = data.get("last_root")
        if isinstance(raw_last_root, str):
            migrated["last_root"] = FolderContext.from_path(
                Path(raw_last_root),
                "folder",
            ).to_dict()

        raw_folders = data.get("folders")
        if not isinstance(raw_folders, dict):
            return migrated

        positions: dict[str, Any] = migrated["positions"]
        for raw_root, raw_position in raw_folders.items():
            if not isinstance(raw_root, str) or not isinstance(raw_position, dict):
                continue

            archive_path = raw_position.get("archive_path")
            member_name = raw_position.get("member_name")
            if not isinstance(archive_path, str) or not isinstance(member_name, str):
                continue

            context = FolderContext.from_path(Path(raw_root), "folder")
            index = raw_position.get("index")
            global_index = (
                index
                if isinstance(index, int) and not isinstance(index, bool) and index >= 0
                else 0
            )
            positions[context.session_key] = SavedPosition(
                container_id=self._container_id(context, Path(archive_path)),
                member_id=member_name,
                container_index=None,
                global_index=global_index,
            ).to_dict()

        return migrated

    def _write(self, data: dict[str, Any]) -> None:
        try:
            payload = json.dumps(data, ensure_ascii=False, indent=2)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            )
        except OSError:
            return

        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
        except OSError:
            try:
                os.close(descriptor)
            except OSError:
                pass
        finally:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _empty_session() -> dict[str, Any]:
    return {"version": SESSION_VERSION, "last_root": None, "positions": {}}


def _normalized_v2(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    normalized["version"] = SESSION_VERSION
    if not isinstance(normalized.get("last_root"), dict):
        normalized["last_root"] = None
    if not isinstance(normalized.get("positions"), dict):
        normalized["positions"] = {}
    return normalized


def _looks_like_v1(data: dict[str, Any]) -> bool:
    version = data.get("version")
    if version not in (None, 1):
        return False
    return isinstance(data.get("last_root"), str) or isinstance(data.get("folders"), dict)


def _resolve_for_identity(path: Path) -> Path:
    try:
        return Path(path).resolve(strict=False)
    except (OSError, RuntimeError):
        return Path(path)
