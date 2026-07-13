from __future__ import annotations

from PySide6.QtGui import QColor, QImage, QPixmap

from zippictureviewer.image_view import MAX_ZOOM, ImageView


def _pixmap(width: int = 200, height: int = 100) -> QPixmap:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#336699"))
    return QPixmap.fromImage(image)


def test_image_view_switches_between_fit_actual_and_zoom(qtbot) -> None:
    view = ImageView()
    qtbot.addWidget(view)
    view.resize(500, 400)
    view.show()

    view.set_pixmap(_pixmap())
    assert view.fit_mode
    assert not view.current_pixmap.isNull()

    view.actual_size()
    assert not view.fit_mode
    assert view.transform().m11() == 1.0

    view.zoom_in()
    assert view.transform().m11() > 1.0

    view.fit_to_window()
    assert view.fit_mode


def test_image_view_message_replaces_previous_pixmap(qtbot) -> None:
    view = ImageView()
    qtbot.addWidget(view)
    view.set_pixmap(_pixmap())

    view.show_message("읽을 수 없는 이미지")

    assert view.current_pixmap.isNull()


def test_zoom_can_recover_from_fit_scales_outside_manual_bounds(qtbot) -> None:
    view = ImageView()
    qtbot.addWidget(view)
    view.set_pixmap(_pixmap())

    view.resetTransform()
    view.scale(0.03, 0.03)
    view.zoom_in()
    assert view.transform().m11() > 0.03

    view.resetTransform()
    view.scale(30.0, 30.0)
    view.zoom_out()
    assert view.transform().m11() < 30.0

    view.resize(500, 400)
    view.set_pixmap(_pixmap(1, 1))
    assert view.transform().m11() <= MAX_ZOOM
