from __future__ import annotations

from collections import OrderedDict

from PySide6.QtGui import QPixmap

from .image_loader import load_pixmap
from .models import ImageEntry


class PixmapCache:
    def __init__(self, max_items: int = 7) -> None:
        self.max_items = max_items
        self._items: OrderedDict[ImageEntry, QPixmap] = OrderedDict()

    def clear(self) -> None:
        self._items.clear()

    def get_or_load(self, entry: ImageEntry) -> QPixmap:
        cached = self._items.get(entry)
        if cached is not None:
            self._items.move_to_end(entry)
            return cached

        pixmap = load_pixmap(entry)
        self._items[entry] = pixmap
        self._trim()
        return pixmap

    def preload_around(
        self,
        entries: list[ImageEntry],
        current_index: int,
        before: int = 2,
        after: int = 3,
    ) -> None:
        if not entries:
            return

        start = max(0, current_index - before)
        stop = min(len(entries), current_index + after + 1)
        for index in range(start, stop):
            entry = entries[index]
            if entry not in self._items:
                try:
                    self.get_or_load(entry)
                except Exception:
                    continue

    def _trim(self) -> None:
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)
