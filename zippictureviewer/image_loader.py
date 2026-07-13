from __future__ import annotations

from dataclasses import dataclass
from math import inf
from zipfile import ZipFile, ZipInfo

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage, QImageReader, QMovie, QPixmap

from .models import ContainerRevision, ImageEntry


MEBIBYTE = 1024 * 1024


class ImageLoadError(ValueError):
    """Base class for failures that can be shown as an image error."""


class ResourceLimitError(ImageLoadError):
    """Raised before an image exceeds a configured resource budget."""


class SourceChangedError(ImageLoadError):
    """Raised when an index entry no longer describes the source on disk."""


@dataclass(frozen=True)
class ImageLoadLimits:
    max_uncompressed_bytes: int = 256 * MEBIBYTE
    max_pixels: int = 100_000_000
    compression_ratio_min_bytes: int = 64 * MEBIBYTE
    max_compression_ratio: float = 500.0
    movie_cache_max_bytes: int = 32 * MEBIBYTE

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_uncompressed_bytes,
            self.max_pixels,
            self.compression_ratio_min_bytes,
            self.movie_cache_max_bytes,
        )
        if any(limit < 0 for limit in integer_limits):
            raise ValueError("Image resource limits cannot be negative")
        if self.max_compression_ratio <= 0:
            raise ValueError("max_compression_ratio must be positive")


DEFAULT_IMAGE_LIMITS = ImageLoadLimits()


@dataclass
class MovieResource:
    movie: QMovie
    byte_array: QByteArray | None = None
    buffer: QBuffer | None = None


def read_image_bytes(
    entry: ImageEntry,
    limits: ImageLoadLimits = DEFAULT_IMAGE_LIMITS,
) -> bytes:
    """Read one exact image member after checking cheap resource limits."""

    _validate_source_revision(entry)
    if not entry.is_archive_member:
        image_path = entry.archive_path / entry.member_name
        size = image_path.stat().st_size
        _validate_uncompressed_size(size, entry.member_name, limits)
        with image_path.open("rb") as image_file:
            image_bytes = _read_bounded(image_file, limits.max_uncompressed_bytes)
    else:
        with ZipFile(entry.archive_path) as archive:
            info = _resolve_archive_info(archive, entry)
            _validate_archive_member(info, limits)
            with archive.open(info) as image_file:
                image_bytes = _read_bounded(
                    image_file,
                    limits.max_uncompressed_bytes,
                )

    _validate_source_revision(entry)
    return image_bytes


def load_image(
    entry: ImageEntry,
    limits: ImageLoadLimits = DEFAULT_IMAGE_LIMITS,
) -> QImage:
    """Decode to a QImage, which is safe to produce in a worker thread."""

    image_bytes = read_image_bytes(entry, limits)
    byte_array, buffer = _read_buffer(image_bytes)
    reader = QImageReader(buffer)
    reader.setAutoTransform(True)

    size = reader.size()
    if size.isValid():
        _validate_pixel_count(size.width(), size.height(), entry.member_name, limits)

    image = reader.read()
    if image.isNull():
        detail = reader.errorString().strip()
        suffix = f" ({detail})" if detail else ""
        raise ImageLoadError(f"Cannot load image: {entry.member_name}{suffix}")
    _validate_pixel_count(image.width(), image.height(), entry.member_name, limits)

    # byte_array and buffer stay local through reader.read(); QImage owns the
    # decoded pixels after this point.
    return image


def load_pixmap(
    entry: ImageEntry,
    limits: ImageLoadLimits = DEFAULT_IMAGE_LIMITS,
) -> QPixmap:
    """GUI-thread compatibility wrapper around :func:`load_image`."""

    return QPixmap.fromImage(load_image(entry, limits))


def load_movie(
    entry: ImageEntry,
    limits: ImageLoadLimits = DEFAULT_IMAGE_LIMITS,
) -> MovieResource:
    image_bytes = read_image_bytes(entry, limits)
    return create_movie_resource(image_bytes, entry.member_name, limits)


def create_movie_resource(
    image_bytes: bytes,
    member_name: str,
    limits: ImageLoadLimits = DEFAULT_IMAGE_LIMITS,
) -> MovieResource:
    """Construct and validate QMovie objects on the GUI thread."""

    _validate_uncompressed_size(len(image_bytes), member_name, limits)
    byte_array, buffer = _read_buffer(image_bytes)
    movie = QMovie(buffer, QByteArray(b"gif"))
    movie.setCacheMode(QMovie.CacheMode.CacheNone)

    if not movie.isValid() or not movie.jumpToFrame(0):
        raise ImageLoadError(f"Cannot load animation: {member_name}")
    first_frame = movie.currentImage()
    if first_frame.isNull():
        raise ImageLoadError(f"Cannot load animation: {member_name}")
    _validate_pixel_count(
        first_frame.width(),
        first_frame.height(),
        member_name,
        limits,
    )
    frame_count = movie.frameCount()
    estimated_cache_bytes = int(first_frame.sizeInBytes()) * max(frame_count, 1)
    if frame_count > 0 and estimated_cache_bytes <= limits.movie_cache_max_bytes:
        movie.setCacheMode(QMovie.CacheMode.CacheAll)

    return MovieResource(movie=movie, byte_array=byte_array, buffer=buffer)


def current_source_revision(entry: ImageEntry) -> ContainerRevision:
    return ContainerRevision.from_path(entry.source_path)


def _resolve_archive_info(archive: ZipFile, entry: ImageEntry) -> ZipInfo:
    member_id = entry.member_id
    if member_id is None:
        return archive.getinfo(entry.member_name)

    infos = archive.infolist()
    if 0 <= member_id.record_index < len(infos):
        candidate = infos[member_id.record_index]
        if _info_matches_id(candidate, member_id.header_offset, member_id.crc):
            return candidate

    matching_infos = [
        info
        for info in infos
        if _info_matches_id(info, member_id.header_offset, member_id.crc)
    ]
    if len(matching_infos) == 1:
        return matching_infos[0]
    raise SourceChangedError(
        f"Archive changed since it was scanned: {entry.archive_path}"
    )


def _info_matches_id(info: ZipInfo, header_offset: int, crc: int) -> bool:
    return info.header_offset == header_offset and info.CRC == crc


def _validate_source_revision(entry: ImageEntry) -> None:
    expected = entry.source_revision
    if expected is None:
        return
    current = current_source_revision(entry)
    if (current.mtime_ns, current.size) != (expected.mtime_ns, expected.size):
        raise SourceChangedError(f"Source changed since it was scanned: {current.path}")


def _validate_archive_member(info: ZipInfo, limits: ImageLoadLimits) -> None:
    _validate_uncompressed_size(info.file_size, info.filename, limits)
    if info.file_size < limits.compression_ratio_min_bytes:
        return

    ratio = inf if info.compress_size == 0 else info.file_size / info.compress_size
    if ratio > limits.max_compression_ratio:
        raise ResourceLimitError(
            f"Compression ratio for {info.filename} is {ratio:.1f}x; "
            f"limit is {limits.max_compression_ratio:.1f}x"
        )


def _validate_uncompressed_size(
    size: int,
    member_name: str,
    limits: ImageLoadLimits,
) -> None:
    if size > limits.max_uncompressed_bytes:
        raise ResourceLimitError(
            f"Uncompressed size for {member_name} is {size} bytes; "
            f"limit is {limits.max_uncompressed_bytes} bytes"
        )


def _validate_pixel_count(
    width: int,
    height: int,
    member_name: str,
    limits: ImageLoadLimits,
) -> None:
    pixels = width * height
    if pixels > limits.max_pixels:
        raise ResourceLimitError(
            f"Pixel count for {member_name} is {pixels}; "
            f"limit is {limits.max_pixels}"
        )


def _read_bounded(source: object, max_bytes: int) -> bytes:
    read = getattr(source, "read")
    data = read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ResourceLimitError(
            f"Decoded data exceeds the {max_bytes}-byte safety limit"
        )
    return data


def _read_buffer(image_bytes: bytes) -> tuple[QByteArray, QBuffer]:
    byte_array = QByteArray(image_bytes)
    buffer = QBuffer(byte_array)
    if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
        raise ImageLoadError("Cannot open image buffer")
    return byte_array, buffer
