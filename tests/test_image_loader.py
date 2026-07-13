from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PySide6.QtGui import QColor, QImage

import zippictureviewer.image_loader as image_loader
from zippictureviewer.archive_scanner import scan_image_index
from zippictureviewer.image_loader import (
    ImageLoadError,
    ImageLoadLimits,
    InvalidPasswordError,
    PasswordRequiredError,
    ResourceLimitError,
    UnsupportedEncryptionError,
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


def test_load_image_uses_the_actual_64_bit_pixel_buffer_size(
    tmp_path: Path,
    qapp,
) -> None:
    image_path = tmp_path / "rgba64.png"
    image = QImage(32, 16, QImage.Format.Format_RGBA64)
    image.fill(QColor("red"))
    assert image.save(str(image_path), "PNG")
    entry = ImageEntry(tmp_path, image_path.name, source_kind="folder")

    with pytest.raises(ResourceLimitError, match="Decoded memory"):
        load_image(
            entry,
            ImageLoadLimits(max_decoded_bytes=32 * 16 * 4),
        )


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


def test_decoded_memory_limit_is_checked_before_reader_allocates(
    tmp_path: Path,
    qapp,
    monkeypatch,
) -> None:
    image_path = tmp_path / "large.png"
    image_path.write_bytes(b"fake image data")
    read_called = False

    class FakeReader:
        def __init__(self, _buffer) -> None:
            pass

        def setAutoTransform(self, _enabled: bool) -> None:  # noqa: N802
            pass

        def size(self) -> QSize:
            return QSize(9000, 8000)

        def setScaledSize(self, _size: QSize) -> None:  # noqa: N802
            pass

        def read(self) -> QImage:
            nonlocal read_called
            read_called = True
            raise AssertionError("reader.read must not run past the memory preflight")

    monkeypatch.setattr(image_loader, "QImageReader", FakeReader)

    with pytest.raises(ResourceLimitError, match="Decoded memory"):
        load_image(ImageEntry(tmp_path, image_path.name, source_kind="folder"))

    assert not read_called


def test_zipcrypto_password_is_session_supplied_and_aes_is_explicit(
    tmp_path: Path,
) -> None:
    encrypted_zip = base64.b64decode(
        "UEsDBAoACQAAAFi97Vxyo8w1LAAAACAAAAAIABwAcGFnZS5wbmdVVAkAA2j5VGpo"
        "+VRqdXgLAAEE9QEAAAQUAAAAABDOj3sL8fFd4NdnJ8TqY2jWOhoO7hym8kaNAT1g"
        "ZH3qsrs+IfdQl2V77UlQSwcIcqPMNSwAAAAgAAAAUEsBAh4DCgAJAAAAWL3tXHKj"
        "zDUsAAAAIAAAAAgAGAAAAAAAAQAAAKSBAAAAAHBhZ2UucG5nVVQFAANo+VRqdXgL"
        "AAEE9QEAAAQUAAAAUEsFBgAAAAABAAEATgAAAH4AAAAAAA=="
    )
    archive_path = tmp_path / "encrypted.zip"
    archive_path.write_bytes(encrypted_zip)
    entry = scan_image_index(archive_path).entries[0]

    assert entry.encryption == "zipcrypto"
    with pytest.raises(PasswordRequiredError):
        read_image_bytes(entry)
    with pytest.raises(InvalidPasswordError):
        read_image_bytes(entry, password=b"wrong")
    with pytest.raises(InvalidPasswordError):
        read_image_bytes(entry, password=b"wrong-123")
    assert read_image_bytes(entry, password=b"secret") == (
        b"not-an-image-but-decryption-test"
    )

    with pytest.raises(UnsupportedEncryptionError, match="AES-encrypted"):
        read_image_bytes(replace(entry, encryption="aes"), password=b"secret")
