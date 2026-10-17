from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from PySide6.QtGui import QImage

from .image_loader import SourceChangedError, current_source_revision
from .models import ContainerRevision, ImageEntry


DEFAULT_CACHE_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class _CacheItem:
    image: QImage
    revision: ContainerRevision
    size_bytes: int
    source_key: Path


class ImageCache:
    """Thread-safe, byte-budgeted cache of decoded images keyed by entry."""

    def __init__(self, max_bytes: int = DEFAULT_CACHE_BYTES) -> None:
        if max_bytes < 0:
            raise ValueError("max_bytes cannot be negative")
        self.max_bytes = max_bytes
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

    def put_image(
        self,
        entry: ImageEntry,
        image: QImage,
        *,
        revision: ContainerRevision | None = None,
    ) -> bool:
        if image.isNull():
            raise ValueError("Cannot cache a null image")

        current_revision = current_source_revision(entry)
        expected_revisions = (entry.source_revision, revision)
        if any(
            expected is not None and expected != current_revision
            for expected in expected_revisions
        ):
            raise SourceChangedError(f"Source changed before caching: {entry.source_path}")
        revision = current_revision
        source_key = _source_key(entry)
        stored_image = QImage(image)
        size_bytes = int(stored_image.sizeInBytes())

        with self._lock:
            self._invalidate_stale_source(source_key, revision)
            self._remove(entry)
            if size_bytes > self.max_bytes:
                return False
            self._items[entry] = _CacheItem(
                image=stored_image,
                revision=revision,
                size_bytes=size_bytes,
                source_key=source_key,
            )
            self._total_bytes += size_bytes
            self._trim()
            return True

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
        while self._total_bytes > self.max_bytes:
            _, item = self._items.popitem(last=False)
            self._total_bytes -= item.size_bytes


def _source_key(entry: ImageEntry) -> Path:
    return _normal_source_key(entry.source_path)


def _normal_source_key(path: Path) -> Path:
    return Path(path).expanduser().absolute()
