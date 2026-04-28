from __future__ import annotations

from dataclasses import dataclass, field

from .models import ImageEntry


@dataclass
class ViewerState:
    entries: list[ImageEntry] = field(default_factory=list)
    current_index: int = 0

    def set_entries(self, entries: list[ImageEntry], current_index: int = 0) -> None:
        self.entries = entries
        self.current_index = self._clamped_index(current_index)

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
        current_entry = self.current_entry
        if current_entry is None:
            return False

        for index in range(self.current_index + 1, len(self.entries)):
            if self.entries[index].archive_path != current_entry.archive_path:
                self.current_index = index
                return True
        self.current_index = 0
        return True

    def move_previous_archive(self) -> bool:
        current_entry = self.current_entry
        if current_entry is None:
            return False

        for index in range(self.current_index - 1, -1, -1):
            if self.entries[index].archive_path != current_entry.archive_path:
                self.current_index = self._first_index_for_archive(
                    self.entries[index].archive_path
                )
                return True
        self.current_index = self._first_index_for_archive(self.entries[-1].archive_path)
        return True

    def has_next_archive(self) -> bool:
        current_entry = self.current_entry
        if current_entry is None:
            return False

        if len({entry.archive_path for entry in self.entries}) > 1:
            return True
        return False

    def has_previous_archive(self) -> bool:
        current_entry = self.current_entry
        if current_entry is None:
            return False

        if len({entry.archive_path for entry in self.entries}) > 1:
            return True
        return False

    def _clamped_index(self, index: int) -> int:
        if not self.entries:
            return 0
        return max(0, min(index, len(self.entries) - 1))

    def _first_index_for_archive(self, archive_path) -> int:
        for index, entry in enumerate(self.entries):
            if entry.archive_path == archive_path:
                return index
        return self.current_index
