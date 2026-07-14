from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

from zippictureviewer.image_view import MAX_ZOOM, ImageView


def _pixmap(width: int = 200, height: int = 100) -> QPixmap:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#336699"))
    return QPixmap.fromImage(image)


def _mouse_event(
    event_type: QEvent.Type,
    global_position: QPoint,
    *,
    button: Qt.MouseButton,
    buttons: Qt.MouseButton,
) -> QMouseEvent:
    local_position = QPointF(20, 20)
    return QMouseEvent(
        event_type,
        local_position,
        local_position,
        QPointF(global_position),
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


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


def test_window_drag_uses_native_system_move_after_the_drag_threshold(
    qtbot,
    monkeypatch,
) -> None:
    view = ImageView()
    qtbot.addWidget(view)
    view.move(80, 60)
    view.show()
    native_move_calls = []
    monkeypatch.setattr(
        view,
        "_start_system_window_move",
        lambda: native_move_calls.append(True) or True,
    )
    start = view.pos() + QPoint(20, 20)
    distance = QApplication.startDragDistance() + 1

    view.mousePressEvent(
        _mouse_event(
            QEvent.Type.MouseButtonPress,
            start,
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.LeftButton,
        )
    )
    view.mouseMoveEvent(
        _mouse_event(
            QEvent.Type.MouseMove,
            start + QPoint(distance, 0),
            button=Qt.MouseButton.NoButton,
            buttons=Qt.MouseButton.LeftButton,
        )
    )

    assert native_move_calls == [True]
    assert view.pos() == QPoint(80, 60)
    assert view._window_drag_offset is None
    assert view._window_drag_origin is None


def test_window_drag_falls_back_to_manual_move_when_native_move_is_unavailable(
    qtbot,
    monkeypatch,
) -> None:
    view = ImageView()
    qtbot.addWidget(view)
    view.move(80, 60)
    view.show()
    monkeypatch.setattr(view, "_start_system_window_move", lambda: False)
    start = view.pos() + QPoint(20, 20)
    distance = QApplication.startDragDistance() + 5
    target = start + QPoint(distance, 7)

    view.mousePressEvent(
        _mouse_event(
            QEvent.Type.MouseButtonPress,
            start,
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.LeftButton,
        )
    )
    view.mouseMoveEvent(
        _mouse_event(
            QEvent.Type.MouseMove,
            target,
            button=Qt.MouseButton.NoButton,
            buttons=Qt.MouseButton.LeftButton,
        )
    )

    assert view.pos() == QPoint(80 + distance, 67)
    assert view._manual_window_drag

    view.mouseReleaseEvent(
        _mouse_event(
            QEvent.Type.MouseButtonRelease,
            target,
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.NoButton,
        )
    )
    assert view._window_drag_offset is None
    assert view._window_drag_origin is None
    assert not view._manual_window_drag


def test_zoomed_image_keeps_pan_behavior_instead_of_moving_the_window(
    qtbot,
    monkeypatch,
) -> None:
    view = ImageView()
    qtbot.addWidget(view)
    view.show()
    view.set_pixmap(_pixmap())
    view.actual_size()
    native_move_calls = []
    monkeypatch.setattr(
        view,
        "_start_system_window_move",
        lambda: native_move_calls.append(True) or True,
    )
    start = view.pos() + QPoint(20, 20)

    view.mousePressEvent(
        _mouse_event(
            QEvent.Type.MouseButtonPress,
            start,
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.LeftButton,
        )
    )

    assert native_move_calls == []
    assert view._window_drag_offset is None
