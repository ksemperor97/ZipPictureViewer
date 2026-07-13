from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

from zippictureviewer.archive_scanner import scan_image_index
from zippictureviewer.image_loader import (
    ImageLoadError,
    ImageLoadLimits,
    ResourceLimitError,
    load_image,
    load_movie,
    read_image_bytes,
)
from zippictureviewer.models import ImageEntry


def _loader_png_bytes(width: int, height: int, color: str = "red") -> bytes:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    return bytes(byte_array)


def test_truncated_gif_must_decode_a_first_frame(tmp_path: Path, qapp) -> None:
    (tmp_path / "broken.gif").write_bytes(b"GIF89a")
    entry = ImageEntry(tmp_path, "broken.gif", source_kind="folder")

    with pytest.raises(ImageLoadError, match="Cannot load animation"):
        load_movie(entry)


def test_load_image_rejects_pixel_limit_before_returning_image(
    tmp_path: Path,
    qapp,
) -> None:
    (tmp_path / "large.png").write_bytes(_loader_png_bytes(4, 3))
    entry = ImageEntry(tmp_path, "large.png", source_kind="folder")
    limits = ImageLoadLimits(max_pixels=11)

    with pytest.raises(ResourceLimitError, match="Pixel count"):
        load_image(entry, limits)


def test_uncompressed_and_compression_ratio_limits_are_enforced(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "compressed.zip"
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("page.png", b"0" * 100_000)
    entry = scan_image_index(tmp_path).entries[0]

    with pytest.raises(ResourceLimitError, match="Uncompressed size"):
        read_image_bytes(
            entry,
            ImageLoadLimits(max_uncompressed_bytes=99_999),
        )

    with pytest.raises(ResourceLimitError, match="Compression ratio"):
        read_image_bytes(
            entry,
            ImageLoadLimits(
                max_uncompressed_bytes=200_000,
                compression_ratio_min_bytes=1,
                max_compression_ratio=2,
            ),
        )


def test_load_image_returns_worker_safe_qimage(tmp_path: Path, qapp) -> None:
    (tmp_path / "page.png").write_bytes(_loader_png_bytes(3, 2, "blue"))
    entry = ImageEntry(tmp_path, "page.png", source_kind="folder")

    image = load_image(entry)

    assert isinstance(image, QImage)
    assert image.size().toTuple() == (3, 2)
    assert image.pixelColor(0, 0) == QColor("blue")
