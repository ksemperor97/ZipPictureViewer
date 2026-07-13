from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut


def install_viewer_shortcuts(window) -> list[QShortcut]:
    image_bindings = (
        (Qt.Key.Key_Left, window.show_previous_image),
        (Qt.Key.Key_Right, window.show_next_image),
        (Qt.Key.Key_Up, window.show_previous_archive),
        (Qt.Key.Key_Down, window.show_next_archive),
        ("Meta+Up", window.open_previous_sibling_folder),
        ("Meta+Down", window.open_next_sibling_folder),
        ("Ctrl+Up", window.open_previous_sibling_folder),
        ("Ctrl+Down", window.open_next_sibling_folder),
        (Qt.Key.Key_Space, window.show_next_image),
        ("0", window.image_view.request_fit),
        ("1", window.image_view.actual_size),
        ("+", window.image_view.zoom_in),
        ("-", window.image_view.zoom_out),
    )
    window_bindings = (
        ("O", window.open_folder),
        ("Ctrl+Shift+O", window.open_archive),
        ("R", window.refresh_source),
        ("F", window.toggle_fullscreen),
        (Qt.Key.Key_Escape, window.exit_fullscreen),
    )
    shortcuts: list[QShortcut] = []
    for sequence, callback in image_bindings:
        shortcut = QShortcut(
            QKeySequence(sequence),
            window.image_view,
            activated=callback,
        )
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcuts.append(shortcut)
    shortcuts.extend(
        QShortcut(QKeySequence(sequence), window, activated=callback)
        for sequence, callback in window_bindings
    )
    return shortcuts
