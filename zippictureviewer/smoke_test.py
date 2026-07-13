from __future__ import annotations

import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage, QImageReader
from PySide6.QtWidgets import QApplication

from .archive_scanner import scan_image_index
from .folder_context import FolderContext
from .image_loader import load_image
from .image_view import ImageView
from .session_store import SessionStore


REQUIRED_IMAGE_FORMATS = frozenset({"gif", "jpeg", "png", "webp"})


def run_smoke_test() -> int:
    """Exercise the packaged Qt runtime without entering the GUI event loop."""

    app = QApplication.instance() or QApplication(["ZipPictureViewer", "--smoke-test"])
    supported_formats = {
        bytes(image_format).decode("ascii").casefold()
        for image_format in QImageReader.supportedImageFormats()
    }
    missing_formats = REQUIRED_IMAGE_FORMATS - supported_formats
    if missing_formats:
        missing = ", ".join(sorted(missing_formats))
        raise RuntimeError(f"Required Qt image plugins are unavailable: {missing}")

    view = ImageView()
    with tempfile.TemporaryDirectory(prefix="zpv-smoke-") as directory:
        root = Path(directory)
        archive_path = root / "smoke.zip"
        with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
            archive.writestr("page.png", _sample_png())

        result = scan_image_index(archive_path)
        if result.issues or len(result.entries) != 1:
            raise RuntimeError(f"Archive scan failed: {result.issues}")
        image = load_image(result.entries[0])
        if image.isNull() or (image.width(), image.height()) != (8, 6):
            raise RuntimeError("Packaged image decoder returned an invalid image")

        context = FolderContext.from_path(archive_path)
        store = SessionStore(root / "session.json")
        store.save_root(context)
        store.save_position(context, result.entries[0], 0, result.entries)
        if store.last_context() != context or store.restore_index(context, result.entries) != 0:
            raise RuntimeError("Session persistence smoke check failed")

    view.deleteLater()
    app.processEvents()
    print("ZipPictureViewer smoke test passed")
    return 0


def _sample_png() -> bytes:
    image = QImage(8, 6, QImage.Format.Format_RGB32)
    image.fill(QColor("#336699"))
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Cannot open smoke-test image buffer")
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Cannot encode smoke-test PNG")
    return bytes(byte_array)
