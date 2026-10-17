"""Commands the end-to-end tests can send to a running window.

Input commands go through the native ``QWindow`` so Qt performs the same hit
testing, shortcut matching and drop-target lookup as for real user input.
Input is posted after the reply because it may open a modal dialog, which
would otherwise block the reply until the test answers that dialog.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QFileOpenEvent,
    QMovie,
)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit


_MODIFIERS = {
    "shift": Qt.KeyboardModifier.ShiftModifier,
    # Qt maps macOS Command to ControlModifier and Control to MetaModifier.
    "ctrl": Qt.KeyboardModifier.ControlModifier,
    "meta": Qt.KeyboardModifier.MetaModifier,
    "alt": Qt.KeyboardModifier.AltModifier,
}


class AutomationCommands:
    def __init__(self, window) -> None:
        self.window = window

    def run(self, command: dict[str, Any]) -> Any:
        name = command["name"]
        handler = getattr(self, f"cmd_{name}", None)
        if handler is None:
            raise ValueError(f"Unknown automation command: {name}")
        return handler(**command.get("params", {}))

    def cmd_state(self) -> dict[str, Any]:
        window = self.window
        state = window.controller.state
        entry = state.current_entry
        context = window.controller.current_context
        view = window.image_view
        movie_resource = window.presenter.current_movie
        modal = QApplication.activeModalWidget()
        return {
            "visible": window.isVisible(),
            "active": window.isActiveWindow(),
            "fullscreen": window.isFullScreen(),
            "source": str(context.logical_path) if context else None,
            "source_kind": context.source_kind if context else None,
            "scanning": window.controller.pending_context is not None,
            "entry_count": len(state.entries),
            "index": state.current_index if entry else None,
            "archive": entry.archive_path.name if entry else None,
            "member": entry.member_name if entry else None,
            "status": window.controls_panel.status_label.text(),
            "file_label": window.info_panel.file_label.full_text,
            "issues_button": window.controls_panel.issues_button.text(),
            "issue_messages": window.status.issue_messages(),
            "message": view.current_message,
            "has_image": not view.current_pixmap.isNull(),
            "movie_running": movie_resource is not None
            and movie_resource.movie.state() == QMovie.MovieState.Running,
            "fit_mode": view.fit_mode,
            "zoom": round(view.transform().m11(), 4),
            "controls_visible": window.controls_panel.isVisible(),
            "modal_title": modal.windowTitle() if modal else None,
            "dialogs": sorted(
                widget.windowTitle()
                for widget in QApplication.topLevelWidgets()
                if widget.isVisible() and widget is not window
            ),
        }

    def cmd_pixel(self, x: float = 0.5, y: float = 0.5) -> str:
        """Return the rendered colour at a fractional viewport position."""

        viewport = self.window.image_view.viewport()
        image = viewport.grab().toImage()
        point = QPoint(int((image.width() - 1) * x), int((image.height() - 1) * y))
        return image.pixelColor(point).name()

    def cmd_activate(self) -> bool:
        """Bring the window to the front, as a user clicking it would."""

        self.window.raise_()
        self.window.activateWindow()
        return self.window.isActiveWindow()

    def cmd_key(self, key: str, modifiers: tuple[str, ...] = ()) -> bool:
        qt_key = getattr(Qt.Key, f"Key_{key}")
        flags = Qt.KeyboardModifier.NoModifier
        for modifier in modifiers:
            flags |= _MODIFIERS[modifier]
        target = QApplication.focusWindow() or self.window.windowHandle()
        QTimer.singleShot(0, lambda: QTest.keyClick(target, qt_key, flags))
        return True

    def cmd_move_mouse(self, x: float = 0.5, y: float = 0.5) -> bool:
        QTest.mouseMove(self.window.windowHandle(), self._window_point(x, y))
        return True

    def cmd_click(self, button: str) -> bool:
        widget = getattr(self.window.controls_panel, button)
        if not widget.isVisible() or not widget.isEnabled():
            raise RuntimeError(f"{button} is not clickable")
        position = widget.mapTo(self.window, widget.rect().center())
        QTimer.singleShot(
            0,
            lambda: QTest.mouseClick(
                self.window.windowHandle(),
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                position,
            ),
        )
        return True

    def cmd_double_click(self, x: float = 0.5, y: float = 0.5) -> bool:
        position = self._window_point(x, y)
        QTimer.singleShot(
            0,
            lambda: QTest.mouseDClick(
                self.window.windowHandle(),
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                position,
            ),
        )
        return True

    def cmd_drop(self, paths: list[str], x: float = 0.5, y: float = 0.5) -> dict:
        """Deliver a drag-and-drop to the native window like the platform does."""

        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(path) for path in paths])
        point = QPointF(self._window_point(x, y))
        action = Qt.DropAction.CopyAction
        buttons = Qt.MouseButton.LeftButton
        modifiers = Qt.KeyboardModifier.NoModifier
        target = self.window.windowHandle()
        enter = QDragEnterEvent(point.toPoint(), action, mime_data, buttons, modifiers)
        QApplication.sendEvent(target, enter)
        move = QDragMoveEvent(point.toPoint(), action, mime_data, buttons, modifiers)
        # Qt's platform drag handling pre-accepts moves after an accepted enter.
        move.setAccepted(enter.isAccepted())
        QApplication.sendEvent(target, move)
        if not move.isAccepted():
            return {"accepted": False}
        drop = QDropEvent(point, action, mime_data, buttons, modifiers)
        QApplication.sendEvent(target, drop)
        return {"accepted": drop.isAccepted()}

    def cmd_file_open(self, path: str) -> bool:
        """Deliver the event macOS sends for Finder "Open With" and Dock drops."""

        QTimer.singleShot(
            0,
            lambda: QApplication.sendEvent(QApplication.instance(), QFileOpenEvent(path)),
        )
        return True

    def cmd_answer_dialog(self, text: str = "", accept: bool = True) -> bool:
        dialog = QApplication.activeModalWidget()
        if not isinstance(dialog, QInputDialog):
            raise RuntimeError("No input dialog is open")
        # Synchronous on purpose: the dialog is deleted once its nested event
        # loop returns, so no reference to it may outlive this call.
        line_edit = dialog.findChild(QLineEdit)
        QTest.keyClicks(line_edit, text)
        key = Qt.Key.Key_Return if accept else Qt.Key.Key_Escape
        QTest.keyClick(line_edit, key)
        return True

    def cmd_close(self) -> bool:
        QTimer.singleShot(0, self.window.close)
        return True

    def _window_point(self, x: float, y: float) -> QPoint:
        return QPoint(int(self.window.width() * x), int(self.window.height() * y))
