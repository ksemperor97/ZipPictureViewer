from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from PySide6.QtGui import QImage, QPixmap

from .image_loader import (
    DEFAULT_IMAGE_LIMITS,
    ImageLoadLimits,
    SourceChangedError,
    current_source_revision,
    load_image,
)
from .models import ContainerRevision, ImageEntry


DEFAULT_CACHE_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class _CacheItem:
    image: QImage
    revision: ContainerRevision
    size_bytes: int
    source_key: Path


class PixmapCache:
    """Thread-safe byte-budgeted QImage cache with a QPixmap compatibility API."""

    def __init__(
        self,
        max_items: int | None = None,
        max_bytes: int = DEFAULT_CACHE_BYTES,
        limits: ImageLoadLimits = DEFAULT_IMAGE_LIMITS,
    ) -> None:
        if max_items is not None and max_items < 1:
            raise ValueError("max_items must be positive or None")
        if max_bytes < 0:
            raise ValueError("max_bytes cannot be negative")
        self.max_items = max_items
        self.max_bytes = max_bytes
        self.limits = limits
        self._items: OrderedDict[ImageEntry, _CacheItem] = OrderedDict()
        self._total_bytes = 0
        self._lock = RLock()

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._total_bytes

    @property
    def item_count(self) -> int:
        with self._lock:
            return len(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._total_bytes = 0

    def invalidate_source(self, source_path: Path) -> None:
        source_key = _normal_source_key(source_path)
        with self._lock:
            for entry, item in list(self._items.items()):
                if item.source_key == source_key:
                    self._remove(entry)

    def get_image(self, entry: ImageEntry) -> QImage | None:
        """Return a fresh cached image, never decoding on a cache miss."""

        source_key = _source_key(entry)
        try:
            revision = current_source_revision(entry)
        except OSError:
            self.invalidate_source(entry.source_path)
            return None

        with self._lock:
            self._invalidate_stale_source(source_key, revision)
            cached = self._items.get(entry)
            if cached is None or cached.revision != revision:
                return None
            self._items.move_to_end(entry)
            return QImage(cached.image)

    def get_or_load_image(self, entry: ImageEntry) -> QImage:
        before_revision = current_source_revision(entry)
        source_key = _source_key(entry)
        with self._lock:
            self._invalidate_stale_source(source_key, before_revision)
            cached = self._items.get(entry)
            if cached is not None and cached.revision == before_revision:
                self._items.move_to_end(entry)
                return QImage(cached.image)

        image = load_image(entry, self.limits)
        after_revision = current_source_revision(entry)
        if after_revision != before_revision:
            raise SourceChangedError(f"Source changed while loading: {entry.source_path}")
        self.put_image(entry, image, revision=after_revision)
        return image

    def put_image(
        self,
        entry: ImageEntry,
        image: QImage,
        *,
        revision: ContainerRevision | None = None,
    ) -> None:
        if image.isNull():
            raise ValueError("Cannot cache a null image")

        current_revision = current_source_revision(entry)
        if revision is not None and revision != current_revision:
            raise SourceChangedError(f"Source changed before caching: {entry.source_path}")
        revision = current_revision
        source_key = _source_key(entry)
        stored_image = QImage(image)
        size_bytes = int(stored_image.sizeInBytes())

        with self._lock:
            self._invalidate_stale_source(source_key, revision)
            self._remove(entry)
            if size_bytes > self.max_bytes:
                return
            self._items[entry] = _CacheItem(
                image=stored_image,
                revision=revision,
                size_bytes=size_bytes,
                source_key=source_key,
            )
            self._total_bytes += size_bytes
            self._trim()

    def get_or_load(self, entry: ImageEntry) -> QPixmap:
        """Return a GUI-thread QPixmap for compatibility with existing UI code."""

        return QPixmap.fromImage(self.get_or_load_image(entry))

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
            if entry.is_animated:
                continue
            try:
                self.get_or_load_image(entry)
            except Exception:
                continue

    def _invalidate_stale_source(
        self,
        source_key: Path,
        revision: ContainerRevision,
    ) -> None:
        for entry, item in list(self._items.items()):
            if item.source_key == source_key and item.revision != revision:
                self._remove(entry)

    def _remove(self, entry: ImageEntry) -> None:
        item = self._items.pop(entry, None)
        if item is not None:
            self._total_bytes -= item.size_bytes

    def _trim(self) -> None:
        while self._total_bytes > self.max_bytes or (
            self.max_items is not None and len(self._items) > self.max_items
        ):
            _, item = self._items.popitem(last=False)
            self._total_bytes -= item.size_bytes


def _source_key(entry: ImageEntry) -> Path:
    return _normal_source_key(entry.source_path)


def _normal_source_key(path: Path) -> Path:
    return Path(path).expanduser().absolute()
