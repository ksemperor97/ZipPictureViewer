from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import ImageEntry


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
    archive_path: str
    member_name: str
    index: int


class SessionStore:
    def __init__(self, path: Path = SESSION_FILE) -> None:
        self.path = path

    def last_root(self) -> Path | None:
        data = self._read()
        raw_root = data.get("last_root")
        if not isinstance(raw_root, str):
            return None

        root = Path(raw_root)
        if not root.is_dir():
            return None
        return root

    def save_position(self, root: Path, entry: ImageEntry, index: int) -> None:
        data = self._read()
        folders = data.setdefault("folders", {})
        if not isinstance(folders, dict):
            folders = {}
            data["folders"] = folders

        data["last_root"] = str(root)
        folders[str(root)] = asdict(
            SavedPosition(
                archive_path=str(entry.archive_path),
                member_name=entry.member_name,
                index=index,
            )
        )
        self._write(data)

    def restore_index(self, root: Path, entries: list[ImageEntry]) -> int:
        data = self._read()
        folders = data.get("folders")
        if not isinstance(folders, dict):
            return 0

        raw_position = folders.get(str(root))
        if not isinstance(raw_position, dict):
            return 0

        restored = self._find_saved_entry(raw_position, entries)
        if restored is not None:
            return restored

        raw_index = raw_position.get("index")
        if isinstance(raw_index, int) and 0 <= raw_index < len(entries):
            return raw_index

        return 0

    def _find_saved_entry(
        self,
        raw_position: dict[str, Any],
        entries: list[ImageEntry],
    ) -> int | None:
        archive_path = raw_position.get("archive_path")
        member_name = raw_position.get("member_name")
        if not isinstance(archive_path, str) or not isinstance(member_name, str):
            return None

        for index, entry in enumerate(entries):
            if str(entry.archive_path) == archive_path and entry.member_name == member_name:
                return index
        return None

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return
