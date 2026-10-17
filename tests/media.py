"""Write real image and ZIP files for end-to-end scenarios.

Everything is encoded by hand so the test process needs neither Qt nor
Pillow, and so encrypted and legacy-encoded archives can be produced exactly.
"""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


RED = (0xFF, 0x00, 0x00)
GREEN = (0x00, 0xFF, 0x00)
BLUE = (0x00, 0x00, 0xFF)
YELLOW = (0xFF, 0xFF, 0x00)


def hex_color(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def png_bytes(rgb: tuple[int, int, int], width: int = 64, height: int = 48) -> bytes:
    row = b"\x00" + bytes(rgb) * width

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )


def write_png(path: Path, rgb: tuple[int, int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes(rgb))
    return path


def animated_gif_bytes(colors: list[tuple[int, int, int]], size: int = 16) -> bytes:
    """Return a looping GIF with one solid frame per colour (max 4 colours)."""

    palette = b"".join(bytes(color) for color in colors)
    palette += b"\x00" * (12 - len(palette))
    data = bytearray(b"GIF89a")
    data += struct.pack("<HHBBB", size, size, 0xF1, 0, 0)  # 4-entry global table
    data += palette
    data += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"
    for index in range(len(colors)):
        data += b"\x21\xf9\x04\x04" + struct.pack("<H", 10) + b"\x00\x00"
        data += b"\x2c" + struct.pack("<HHHHB", 0, 0, size, size, 0)
        data += b"\x02" + _gif_sub_blocks(_lzw_literals([index] * size * size))
    data += b"\x3b"
    return bytes(data)


def _lzw_literals(pixels: list[int]) -> bytes:
    # Re-sending CLEAR every two pixels keeps the code width at 3 bits, which
    # avoids implementing real LZW compression.
    clear, end = 4, 5
    codes: list[int] = []
    for start in range(0, len(pixels), 2):
        codes.append(clear)
        codes.extend(pixels[start : start + 2])
    codes.append(end)
    bits = 0
    bit_count = 0
    output = bytearray()
    for code in codes:
        bits |= code << bit_count
        bit_count += 3
        while bit_count >= 8:
            output.append(bits & 0xFF)
            bits >>= 8
            bit_count -= 8
    if bit_count:
        output.append(bits & 0xFF)
    return bytes(output)


def _gif_sub_blocks(payload: bytes) -> bytes:
    blocks = bytearray()
    for start in range(0, len(payload), 255):
        piece = payload[start : start + 255]
        blocks += bytes([len(piece)]) + piece
    return bytes(blocks) + b"\x00"


def write_zip(path: Path, members: dict[str, bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return path


def write_book(path: Path, colors: list[tuple[int, int, int]]) -> Path:
    """Write an archive whose pages are p1.png, p2.png, ... in ``colors``."""

    pages = {f"p{number}.png": png_bytes(color) for number, color in enumerate(colors, 1)}
    return write_zip(path, pages)


def write_raw_zip(path: Path, members: list[tuple]) -> Path:
    """Write members as ``(raw_name, stored_data, flag_bits, method[, crc, size])``.

    ``stored_data`` is written verbatim, which allows ZipCrypto payloads,
    an AES method marker and names without the UTF-8 flag. ``crc`` and
    ``size`` describe the plain data and default to those of ``stored_data``.
    """

    local_records = bytearray()
    central_records = bytearray()
    for raw_name, stored, flags, method, crc, size in _with_sizes(members):
        offset = len(local_records)
        local_records += struct.pack(
            "<IHHHHHIIIHH", 0x04034B50, 20, flags, method, 0, 0x21,
            crc, len(stored), size, len(raw_name), 0,
        ) + raw_name + stored
        central_records += struct.pack(
            "<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, flags, method, 0, 0x21,
            crc, len(stored), size, len(raw_name), 0, 0, 0, 0, 0, offset,
        ) + raw_name
    end = struct.pack(
        "<IHHHHIIH", 0x06054B50, 0, 0, len(members), len(members),
        len(central_records), len(local_records), 0,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(local_records + central_records + end))
    return path


def _with_sizes(members):
    for raw_name, stored, flags, method, *rest in members:
        crc, size = rest if rest else (zlib.crc32(stored), len(stored))
        yield raw_name, stored, flags, method, crc, size


def write_zipcrypto_zip(path: Path, name: str, payload: bytes, password: str) -> Path:
    crc = zlib.crc32(payload)
    header = bytearray(os.urandom(11)) + bytes([crc >> 24])
    encrypted = _ZipCrypto(password.encode()).encrypt(bytes(header) + payload)
    member = (name.encode(), encrypted, 0x1, 0, crc, len(payload))
    return write_raw_zip(path, [member])


def write_aes_marked_zip(path: Path, name: str) -> Path:
    # Method 99 with the encryption flag is how WinZip AES archives present.
    return write_raw_zip(path, [(name.encode(), b"\x00" * 32, 0x1, 99, 0, 16)])


class _ZipCrypto:
    """Traditional PKWARE encryption, which Python's zipfile cannot write."""

    def __init__(self, password: bytes) -> None:
        self.keys = [0x12345678, 0x23456789, 0x34567890]
        for byte in password:
            self._update(byte)

    def _crc(self, crc: int, byte: int) -> int:
        return (crc >> 8) ^ _CRC_TABLE[(crc ^ byte) & 0xFF]

    def _update(self, byte: int) -> None:
        k0, k1, k2 = self.keys
        k0 = self._crc(k0, byte)
        k1 = ((k1 + (k0 & 0xFF)) * 134775813 + 1) & 0xFFFFFFFF
        k2 = self._crc(k2, k1 >> 24)
        self.keys = [k0, k1, k2]

    def encrypt(self, plain: bytes) -> bytes:
        output = bytearray()
        for byte in plain:
            temp = (self.keys[2] | 2) & 0xFFFF
            output.append(byte ^ (((temp * (temp ^ 1)) >> 8) & 0xFF))
            self._update(byte)
        return bytes(output)


def _crc_table() -> list[int]:
    table = []
    for index in range(256):
        value = index
        for _ in range(8):
            value = (value >> 1) ^ 0xEDB88320 if value & 1 else value >> 1
        table.append(value)
    return table


_CRC_TABLE = _crc_table()


def write_zip64_locator_only(path: Path, record_offset: int) -> Path:
    """A ZIP whose end record defers to a ZIP64 record at ``record_offset``."""

    locator = struct.pack("<IIQI", 0x07064B50, 0, record_offset, 1)
    end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(locator + end)
    return path


def write_zip64_member(
    path: Path,
    name: str,
    *,
    uncompressed: int,
    compressed: int,
    offset: int | None = None,
    method: int = 8,
) -> Path:
    """One member whose ZIP64 extra field declares the given sizes.

    A real local header is written at offset 0 so readers get past the
    header check; ``offset`` overrides the declared local header offset.
    """

    raw_name = name.encode()
    local = struct.pack(
        "<IHHHHHIIIHH", 0x04034B50, 45, 0x0800, method, 0, 0x21,
        0, 0xFFFFFFFF, 0xFFFFFFFF, len(raw_name), 0,
    ) + raw_name
    extra = struct.pack("<HHQQQ", 0x0001, 24, uncompressed, compressed, offset or 0)
    central = struct.pack(
        "<IHHHHHHIIIHHHHHII", 0x02014B50, 45, 45, 0x0800, method, 0, 0x21,
        0, 0xFFFFFFFF, 0xFFFFFFFF, len(raw_name), len(extra), 0, 0, 0, 0, 0xFFFFFFFF,
    ) + raw_name + extra
    end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 1, 1, len(central), len(local), 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(local + central + end)
    return path
