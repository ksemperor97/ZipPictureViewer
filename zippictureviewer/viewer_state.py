from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path

from .models import ImageEntry


@dataclass
class ViewerState:
    entries: list[ImageEntry] = field(default_factory=list)
    current_index: int = 0
    _archive_starts: list[int] = field(default_factory=list, init=False, repr=False)
    _archive_paths: list[Path] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self.current_index = self._clamped_index(self.current_index)
        self._rebuild_archive_index()

    def set_entries(self, entries: list[ImageEntry], current_index: int = 0) -> None:
        self.entries = entries
        self.current_index = self._clamped_index(current_index)
        self._rebuild_archive_index()

    @property
    def has_entries(self) -> bool:
        return bool(self.entries)

    @property
    def current_entry(self) -> ImageEntry | None:
        if not self.entries:
            return None
        return self.entries[self.current_index]

    @property
    def position_label(self) -> str:
        if not self.entries:
            return "0 / 0"
        return f"{self.current_index + 1} / {len(self.entries)}"

    def move_next(self) -> bool:
        if not self.entries:
            return False
        if self.current_index >= len(self.entries) - 1:
            self.current_index = 0
            return True
        self.current_index += 1
        return True

    def move_previous(self) -> bool:
        if self.current_index <= 0:
            return False
        self.current_index -= 1
        return True

    def move_next_archive(self) -> bool:
        if len(self._archive_starts) <= 1:
            return False
        archive_index = self._current_archive_index()
        self.current_index = self._archive_starts[
            (archive_index + 1) % len(self._archive_starts)
        ]
        return True

    def move_previous_archive(self) -> bool:
        if len(self._archive_starts) <= 1:
            return False
        archive_index = self._current_archive_index()
        self.current_index = self._archive_starts[
            (archive_index - 1) % len(self._archive_starts)
        ]
        return True

    def has_next_archive(self) -> bool:
        return len(self._archive_starts) > 1

    def has_previous_archive(self) -> bool:
        return len(self._archive_starts) > 1

    def _clamped_index(self, index: int) -> int:
        if not self.entries:
            return 0
        return max(0, min(index, len(self.entries) - 1))

    def _rebuild_archive_index(self) -> None:
        self._archive_starts.clear()
        self._archive_paths.clear()
        previous_path: Path | None = None
        for index, entry in enumerate(self.entries):
            if index == 0 or entry.archive_path != previous_path:
                self._archive_starts.append(index)
                self._archive_paths.append(entry.archive_path)
            previous_path = entry.archive_path

    def _current_archive_index(self) -> int:
        return max(0, bisect_right(self._archive_starts, self.current_index) - 1)
