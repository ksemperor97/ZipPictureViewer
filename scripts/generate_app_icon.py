from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT_DIR / "assets"
ICONSET_DIR = ASSETS_DIR / "ZipPictureViewer.iconset"
ICNS_PATH = ASSETS_DIR / "ZipPictureViewer.icns"
ICO_PATH = ASSETS_DIR / "ZipPictureViewer.ico"


ICON_SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication([])

    ASSETS_DIR.mkdir(exist_ok=True)

    large = draw_icon(1024)
    write_ico(large)
    if platform.system() == "Darwin":
        write_icns(large)

    print(ICNS_PATH if ICNS_PATH.exists() else ICO_PATH)
    app.quit()


def write_icns(large: QImage) -> None:
    ICONSET_DIR.mkdir(exist_ok=True)
    for filename, size in ICON_SIZES.items():
        scaled = large.scaled(
            size,
            size,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.save(str(ICONSET_DIR / filename))

    subprocess.run(["iconutil", "-c", "icns", str(ICONSET_DIR), "-o", str(ICNS_PATH)], check=True)


def write_ico(large: QImage) -> None:
    icon = large.scaled(
        256,
        256,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    if not icon.save(str(ICO_PATH), "ICO"):
        raise RuntimeError(f"Failed to write Windows icon: {ICO_PATH}")


def draw_icon(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    draw_background(painter, size)
    draw_photo_stack(painter, size)
    draw_zipper(painter, size)

    painter.end()
    return image


def draw_background(painter: QPainter, size: int) -> None:
    rect = QRectF(size * 0.09, size * 0.08, size * 0.82, size * 0.82)
    radius = size * 0.18
    path = rounded_rect(rect, radius)

    shadow = rounded_rect(rect.translated(0, size * 0.035), radius)
    painter.fillPath(shadow, QColor(0, 0, 0, 55))

    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor("#2dd4bf"))
    gradient.setColorAt(0.48, QColor("#2563eb"))
    gradient.setColorAt(1.0, QColor("#1e293b"))
    painter.fillPath(path, gradient)

    painter.setPen(QPen(QColor(255, 255, 255, 80), size * 0.012))
    painter.drawPath(path)


def draw_photo_stack(painter: QPainter, size: int) -> None:
    back_rect = QRectF(size * 0.25, size * 0.22, size * 0.48, size * 0.57)
    front_rect = QRectF(size * 0.19, size * 0.28, size * 0.54, size * 0.54)

    painter.save()
    painter.translate(size * 0.03, -size * 0.005)
    painter.rotate(7)
    draw_photo_card(painter, back_rect, size, faded=True)
    painter.restore()

    painter.save()
    painter.rotate(-5)
    painter.translate(-size * 0.055, size * 0.035)
    draw_photo_card(painter, front_rect, size, faded=False)
    painter.restore()


def draw_photo_card(painter: QPainter, rect: QRectF, size: int, faded: bool) -> None:
    radius = size * 0.045
    path = rounded_rect(rect, radius)
    painter.fillPath(path.translated(0, size * 0.018), QColor(0, 0, 0, 45))
    painter.fillPath(path, QColor(248, 250, 252, 225 if faded else 255))

    inner = rect.adjusted(size * 0.045, size * 0.045, -size * 0.045, -size * 0.12)
    inner_path = rounded_rect(inner, size * 0.03)
    sky = QLinearGradient(inner.topLeft(), inner.bottomLeft())
    sky.setColorAt(0.0, QColor("#7dd3fc"))
    sky.setColorAt(0.55, QColor("#22c55e"))
    sky.setColorAt(1.0, QColor("#166534"))
    painter.fillPath(inner_path, sky)

    mountain = QPainterPath()
    mountain.moveTo(inner.left(), inner.bottom())
    mountain.lineTo(inner.left() + inner.width() * 0.35, inner.top() + inner.height() * 0.45)
    mountain.lineTo(inner.left() + inner.width() * 0.62, inner.bottom())
    mountain.closeSubpath()
    painter.fillPath(mountain, QColor("#14532d"))

    mountain2 = QPainterPath()
    mountain2.moveTo(inner.left() + inner.width() * 0.3, inner.bottom())
    mountain2.lineTo(inner.left() + inner.width() * 0.75, inner.top() + inner.height() * 0.35)
    mountain2.lineTo(inner.right(), inner.bottom())
    mountain2.closeSubpath()
    painter.fillPath(mountain2, QColor("#15803d"))

    painter.setPen(QPen(QColor(226, 232, 240), size * 0.012))
    painter.drawPath(path)


def draw_zipper(painter: QPainter, size: int) -> None:
    x = size * 0.69
    top = size * 0.20
    bottom = size * 0.77
    width = size * 0.075

    rail = rounded_rect(QRectF(x, top, width, bottom - top), size * 0.035)
    painter.fillPath(rail.translated(size * 0.012, size * 0.018), QColor(0, 0, 0, 55))
    painter.fillPath(rail, QColor("#f8fafc"))
    painter.setPen(QPen(QColor("#0f172a"), size * 0.01))
    painter.drawPath(rail)

    tooth_h = size * 0.033
    gap = size * 0.012
    y = top + size * 0.045
    toggle = False
    while y < bottom - size * 0.09:
        tx = x + (width * 0.12 if toggle else width * 0.48)
        painter.fillRect(QRectF(tx, y, width * 0.40, tooth_h), QColor("#334155"))
        y += tooth_h + gap
        toggle = not toggle

    pull = rounded_rect(QRectF(x - width * 0.2, bottom - size * 0.085, width * 1.4, size * 0.09), size * 0.025)
    painter.fillPath(pull, QColor("#f59e0b"))
    painter.setPen(QPen(QColor("#78350f"), size * 0.012))
    painter.drawPath(pull)

    font = QFont("Helvetica Neue", int(size * 0.052))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#0f172a"))
    painter.drawText(QRectF(x - width * 0.18, bottom - size * 0.082, width * 1.36, size * 0.08), Qt.AlignmentFlag.AlignCenter, "ZIP")


def rounded_rect(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


if __name__ == "__main__":
    main()
