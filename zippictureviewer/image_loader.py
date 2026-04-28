from __future__ import annotations

from zipfile import ZipFile

from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtCore import QByteArray, QBuffer, QIODevice

from .models import ImageEntry


def load_pixmap(entry: ImageEntry) -> QPixmap:
    if entry.archive_path.is_dir():
        image_bytes = (entry.archive_path / entry.member_name).read_bytes()
    else:
        with ZipFile(entry.archive_path) as archive:
            image_bytes = archive.read(entry.member_name)

    byte_array = QByteArray(image_bytes)
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)

    reader = QImageReader(buffer)
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ValueError(f"Cannot load image: {entry.member_name}")

    return QPixmap.fromImage(image)
