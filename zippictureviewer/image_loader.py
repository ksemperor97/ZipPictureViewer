from __future__ import annotations

from dataclasses import dataclass
from zipfile import ZipFile

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImageReader, QMovie, QPixmap

from .models import ImageEntry


@dataclass
class MovieResource:
    movie: QMovie
    byte_array: QByteArray | None = None
    buffer: QBuffer | None = None


def read_image_bytes(entry: ImageEntry) -> bytes:
    if entry.archive_path.is_dir():
        return (entry.archive_path / entry.member_name).read_bytes()

    with ZipFile(entry.archive_path) as archive:
        return archive.read(entry.member_name)


def load_pixmap(entry: ImageEntry) -> QPixmap:
    image_bytes = read_image_bytes(entry)
    byte_array = QByteArray(image_bytes)
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)

    reader = QImageReader(buffer)
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ValueError(f"Cannot load image: {entry.member_name}")

    return QPixmap.fromImage(image)


def load_movie(entry: ImageEntry) -> MovieResource:
    if entry.archive_path.is_dir():
        movie = QMovie(str(entry.archive_path / entry.member_name))
        movie.setCacheMode(QMovie.CacheMode.CacheAll)
        if not movie.isValid():
            raise ValueError(f"Cannot load animation: {entry.member_name}")
        return MovieResource(movie=movie)

    byte_array = QByteArray(read_image_bytes(entry))
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    movie = QMovie(buffer, QByteArray(b"gif"))
    movie.setCacheMode(QMovie.CacheMode.CacheAll)
    if not movie.isValid():
        raise ValueError(f"Cannot load animation: {entry.member_name}")

    return MovieResource(movie=movie, byte_array=byte_array, buffer=buffer)
