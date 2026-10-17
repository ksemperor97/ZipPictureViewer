from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)


class ViewerShortcutManager(QObject):
    """Keep viewer commands window-wide without stealing input-widget keys."""

    def __init__(self, window) -> None:
        super().__init__(window)
        self._navigation_shortcuts: list[QShortcut] = []
        self._space_shortcut: QShortcut | None = None

        image_bindings = (
            (Qt.Key.Key_Left, window.show_previous_image),
            (Qt.Key.Key_Right, window.show_next_image),
            (Qt.Key.Key_Up, window.show_previous_archive),
            (Qt.Key.Key_Down, window.show_next_archive),
            ("Meta+Up", window.open_previous_sibling_folder),
            ("Meta+Down", window.open_next_sibling_folder),
            ("Ctrl+Up", window.open_previous_sibling_folder),
            ("Ctrl+Down", window.open_next_sibling_folder),
            ("0", window.image_view.request_fit),
            ("1", window.image_view.actual_size),
            ("+", window.image_view.zoom_in),
            ("-", window.image_view.zoom_out),
        )
        for sequence, callback in image_bindings:
            self._navigation_shortcuts.append(
                self._window_shortcut(window, sequence, callback)
            )
        self._space_shortcut = self._window_shortcut(
            window,
            Qt.Key.Key_Space,
            window.show_next_image,
        )

        for sequence, callback in (
            ("O", window.open_folder),
            ("Ctrl+Shift+O", window.open_archive),
            ("R", window.refresh_source),
            ("F", window.toggle_fullscreen),
            ("?", window.show_shortcut_help),
            (Qt.Key.Key_Escape, window.exit_fullscreen),
        ):
            self._window_shortcut(window, sequence, callback)

        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._sync_focus)
            self._sync_focus(None, app.focusWidget())

    @staticmethod
    def _window_shortcut(window, sequence, callback) -> QShortcut:
        shortcut = QShortcut(QKeySequence(sequence), window, activated=callback)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        return shortcut

    @Slot(QWidget, QWidget)
    def _sync_focus(self, _previous: QWidget | None, current: QWidget | None) -> None:
        editing = _is_input_widget(current)
        for shortcut in self._navigation_shortcuts:
            shortcut.setEnabled(not editing)
        if self._space_shortcut is not None:
            self._space_shortcut.setEnabled(
                not editing and not isinstance(current, QAbstractButton)
            )


def install_viewer_shortcuts(window) -> ViewerShortcutManager:
    return ViewerShortcutManager(window)


def _is_input_widget(widget: QWidget | None) -> bool:
    current = widget
    input_types = (QComboBox, QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)
    while current is not None:
        if isinstance(current, input_types):
            return True
        current = current.parentWidget()
    return False
