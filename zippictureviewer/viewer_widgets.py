from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QSize, QTimer
from PySide6.QtWidgets import QFrame, QSizeGrip, QWidget

from .image_view import ImageView


class FloatingPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self.setStyleSheet(
            """
            QFrame {
                background-color: rgba(24, 24, 27, 205);
                border: 1px solid rgba(255, 255, 255, 35);
                border-radius: 8px;
            }
            QLabel {
                color: #f4f4f5;
                background: transparent;
                border: none;
            }
            QPushButton {
                color: #f4f4f5;
                background-color: rgba(255, 255, 255, 24);
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 6px;
                padding: 6px 10px;
                min-width: 52px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 42);
            }
            QPushButton:disabled {
                color: rgba(244, 244, 245, 90);
                background-color: rgba(255, 255, 255, 12);
            }
            QComboBox {
                color: #f4f4f5;
                background-color: rgba(255, 255, 255, 24);
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 6px;
                padding: 5px 8px;
            }
            QComboBox QAbstractItemView {
                color: #f4f4f5;
                background-color: #27272a;
                selection-background-color: #3f3f46;
            }
            """
        )


class ViewerSurface(QWidget):
    def __init__(
        self,
        image_view: ImageView,
        controls_panel: QWidget,
        info_panel: QWidget,
    ) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self.image_view = image_view
        self.controls_panel = controls_panel
        self.info_panel = info_panel
        self.resize_grip = QSizeGrip(self)
        self.resize_grip.setMouseTracking(True)

        self.image_view.setParent(self)
        self.controls_panel.setParent(self)
        self.info_panel.setParent(self)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.image_view.setGeometry(self.rect())
        self.position_floating_panels()

    def position_floating_panels(self) -> None:
        margin = 12
        max_width = max(0, self.width() - margin * 2)

        self.controls_panel.adjustSize()
        controls_size = self.controls_panel.sizeHint()
        controls_width = min(controls_size.width(), max_width)
        self.controls_panel.setGeometry(
            max(margin, self.width() - controls_width - margin),
            margin,
            controls_width,
            controls_size.height(),
        )

        self.info_panel.adjustSize()
        info_size = self.info_panel.sizeHint()
        grip_clearance = 36
        info_max_width = max(0, max_width - grip_clearance)
        info_width = min(info_size.width(), info_max_width)
        self.info_panel.setGeometry(
            max(
                margin,
                self.width() - info_width - margin - grip_clearance,
            ),
            max(margin, self.height() - info_size.height() - margin),
            info_width,
            info_size.height(),
        )
        self.resize_grip.setGeometry(
            max(0, self.width() - 28),
            max(0, self.height() - 28),
            24,
            24,
        )
        self.controls_panel.raise_()
        self.info_panel.raise_()
        self.resize_grip.raise_()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(1100, 800)


class OverlayController(QObject):
    """Manage transient panels and the frameless-window resize grip."""

    def __init__(
        self,
        surface: ViewerSurface,
        is_fullscreen: Callable[[], bool],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.surface = surface
        self.controls_panel = surface.controls_panel
        self.info_panel = surface.info_panel
        self.is_fullscreen = is_fullscreen
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def show_temporarily(self) -> None:
        self.set_visible(True)
        self.timer.start(2200)

    def hide(self) -> None:
        if self.controls_panel.underMouse() or self.info_panel.underMouse():
            self.timer.start(800)
            return
        self.set_visible(False)

    def set_visible(self, visible: bool) -> None:
        self.controls_panel.setVisible(visible)
        has_info = bool(self.info_panel.file_label.text())
        self.info_panel.setVisible(visible and has_info)
        self.sync_grip(visible)

    def sync_grip(self, overlays_visible: bool | None = None) -> None:
        visible = (
            self.controls_panel.isVisible()
            if overlays_visible is None
            else overlays_visible
        )
        self.surface.resize_grip.setVisible(
            visible and not self.is_fullscreen()
        )

    def stop(self) -> None:
        self.timer.stop()
