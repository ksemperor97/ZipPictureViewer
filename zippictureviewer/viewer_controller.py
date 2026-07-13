from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .folder_context import FolderContext
from .models import ImageEntry
from .viewer_state import ViewerState


@dataclass(frozen=True)
class DisplayToken:
    generation: int
    entry: ImageEntry


class ViewerController:
    """Own transactional source loading and stale-result rejection."""

    def __init__(self) -> None:
        self.state = ViewerState()
        self.current_context: FolderContext | None = None
        self.pending_context: FolderContext | None = None
        self.scan_issues: list[object] = []
        self._load_generation = 0
        self._display_generation = 0

    @property
    def load_generation(self) -> int:
        return self._load_generation

    @property
    def display_generation(self) -> int:
        return self._display_generation

    def begin_load(self, context: FolderContext) -> int:
        self._load_generation += 1
        self.pending_context = context
        return self._load_generation

    def apply_load(
        self,
        generation: int,
        entries: Sequence[ImageEntry],
        issues: Sequence[object] = (),
        current_index: int = 0,
    ) -> bool:
        if generation != self._load_generation or self.pending_context is None:
            return False

        self.current_context = self.pending_context
        self.pending_context = None
        self.scan_issues = list(issues)
        self.state.set_entries(list(entries), current_index)
        self._display_generation += 1
        return True

    def reject_load(self, generation: int) -> bool:
        if generation != self._load_generation:
            return False
        self.pending_context = None
        return True

    def begin_display(self) -> DisplayToken | None:
        entry = self.state.current_entry
        if entry is None:
            return None
        self._display_generation += 1
        return DisplayToken(self._display_generation, entry)

    def is_current_display(self, token: DisplayToken) -> bool:
        return (
            token.generation == self._display_generation
            and token.entry == self.state.current_entry
        )

    def is_current_generation(self, token: DisplayToken) -> bool:
        return token.generation == self._display_generation

    def invalidate_display(self) -> None:
        self._display_generation += 1
