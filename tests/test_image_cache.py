from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtGui import QColor, QImage

import zippictureviewer.image_cache as image_cache
from zippictureviewer.archive_scanner import scan_image_index
from zippictureviewer.image_cache import PixmapCache
from zippictureviewer.models import ImageEntry


def _cache_image_file(path: Path, color: str, size: int = 4) -> None:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    assert image.save(str(path), "PNG")


def test_cache_uses_byte_budget_instead_of_unbounded_item_count(
    tmp_path: Path,
    qapp,
) -> None:
    first_path = tmp_path / "1.png"
    second_path = tmp_path / "2.png"
    _cache_image_file(first_path, "red")
    _cache_image_file(second_path, "blue")
    entries = scan_image_index(tmp_path).entries
    cache = PixmapCache(max_bytes=64)

    cache.get_or_load_image(entries[0])
    cache.get_or_load_image(entries[1])

    assert cache.item_count == 1
    assert cache.total_bytes == 64


def test_changed_source_revision_invalidates_stale_cached_image(
    tmp_path: Path,
    qapp,
) -> None:
    image_path = tmp_path / "page.png"
    _cache_image_file(image_path, "red")
    old_entry = scan_image_index(tmp_path).entries[0]
    cache = PixmapCache(max_bytes=1024)
    old_image = cache.get_or_load_image(old_entry)
    old_stat = image_path.stat()

    _cache_image_file(image_path, "blue")
    newer_mtime = max(image_path.stat().st_mtime_ns, old_stat.st_mtime_ns + 1_000_000)
    os.utime(image_path, ns=(newer_mtime, newer_mtime))
    new_entry = scan_image_index(tmp_path).entries[0]
    new_image = cache.get_or_load_image(new_entry)

    assert old_entry.source_revision != new_entry.source_revision
    assert old_image.pixelColor(0, 0) == QColor("red")
    assert new_image.pixelColor(0, 0) == QColor("blue")
    assert cache.item_count == 1


def test_image_larger_than_budget_is_returned_but_not_cached(
    tmp_path: Path,
    qapp,
) -> None:
    image_path = tmp_path / "large.png"
    _cache_image_file(image_path, "green", size=8)
    entry = ImageEntry(tmp_path, image_path.name, source_kind="folder")
    cache = PixmapCache(max_bytes=128)

    image = cache.get_or_load_image(entry)

    assert image.sizeInBytes() == 256
    assert cache.item_count == 0
    assert cache.total_bytes == 0


def test_get_image_never_decodes_and_rejects_a_stale_revision(
    tmp_path: Path,
    qapp,
    monkeypatch,
) -> None:
    image_path = tmp_path / "page.png"
    _cache_image_file(image_path, "red")
    entry = scan_image_index(tmp_path).entries[0]
    cache = PixmapCache(max_bytes=1024)
    cached_image = QImage(4, 4, QImage.Format.Format_ARGB32)
    cached_image.fill(QColor("red"))
    cache.put_image(entry, cached_image)
    monkeypatch.setattr(
        image_cache,
        "load_image",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("decoded")),
    )

    assert cache.get_image(entry).pixelColor(0, 0) == QColor("red")

    old_stat = image_path.stat()
    _cache_image_file(image_path, "blue")
    newer_mtime = max(image_path.stat().st_mtime_ns, old_stat.st_mtime_ns + 1_000_000)
    os.utime(image_path, ns=(newer_mtime, newer_mtime))

    assert cache.get_image(entry) is None
    assert cache.item_count == 0


def test_atomic_same_size_same_mtime_replacement_invalidates_cache(
    tmp_path: Path,
    qapp,
) -> None:
    image_path = tmp_path / "page.png"
    replacement = tmp_path / "replacement.png"
    _cache_image_file(image_path, "red")
    _cache_image_file(replacement, "blue")
    assert replacement.stat().st_size == image_path.stat().st_size

    entry = scan_image_index(tmp_path).entries[0]
    cache = PixmapCache(max_bytes=1024)
    assert cache.get_or_load_image(entry).pixelColor(0, 0) == QColor("red")
    old_mtime = image_path.stat().st_mtime_ns
    os.utime(replacement, ns=(old_mtime, old_mtime))
    os.replace(replacement, image_path)

    assert image_path.stat().st_mtime_ns == old_mtime
    assert cache.get_image(entry) is None
    new_entry = scan_image_index(tmp_path).entries[0]
    assert cache.get_or_load_image(new_entry).pixelColor(0, 0) == QColor("blue")
