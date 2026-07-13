from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QMovie, QPainter, QPixmap, QResizeEvent, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)


MIN_ZOOM = 0.05
MAX_ZOOM = 20.0
ZOOM_STEP = 1.2


class ImageView(QGraphicsView):
    """Image surface with fit, actual-size, zoom, pan, and movie support."""

    actual_size_requested = Signal()
    fit_requested = Signal()
    viewport_resized = Signal(QSize)
    zoom_resolution_requested = Signal()

    def __init__(self) -> None:
        scene = QGraphicsScene()
        super().__init__(scene)
        self._scene = scene
        self._pixmap_item = QGraphicsPixmapItem()
        self._message_item = QGraphicsTextItem()
        self._scene.addItem(self._pixmap_item)
        self._scene.addItem(self._message_item)

        self._movie: QMovie | None = None
        self._movie_frame_size = QSize()
        self._fit_mode = True
        self._window_drag_offset: QPoint | None = None

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setBackgroundBrush(QColor("#171717"))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setMinimumSize(320, 240)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._message_item.setDefaultTextColor(QColor("#f4f4f5"))
        self._message_item.setZValue(1)
        self.show_message("폴더 열기 또는 드래그")

    @property
    def fit_mode(self) -> bool:
        return self._fit_mode

    @property
    def current_pixmap(self) -> QPixmap:
        return self._pixmap_item.pixmap()

    @property
    def current_message(self) -> str:
        return self._message_item.toPlainText() if self._message_item.isVisible() else ""

    def set_pixmap(self, pixmap: QPixmap, *, reset_view: bool = True) -> None:
        self._detach_movie()
        self._message_item.hide()
        self._pixmap_item.show()
        self._pixmap_item.setPixmap(pixmap)
        self._sync_scene_rect()
        if reset_view:
            self.fit_to_window()

    def set_movie(self, movie: QMovie) -> None:
        self._detach_movie()
        self._movie = movie
        self._movie_frame_size = QSize()
        movie.frameChanged.connect(self._update_movie_frame)
        self._message_item.hide()
        self._pixmap_item.show()
        if movie.currentPixmap().isNull():
            movie.jumpToFrame(0)
        self._update_movie_frame()
        if movie.state() != QMovie.MovieState.Running:
            movie.start()

    def clear_content(self) -> None:
        self._detach_movie()
        self._pixmap_item.setPixmap(QPixmap())
        self._pixmap_item.hide()
        self._message_item.hide()
        self.resetTransform()
        self._scene.setSceneRect(QRectF())

    def show_message(self, message: str) -> None:
        self._detach_movie()
        self._pixmap_item.setPixmap(QPixmap())
        self._pixmap_item.hide()
        self._message_item.setPlainText(message)
        self._message_item.show()
        self.resetTransform()
        self._fit_mode = True
        self._position_message()

    def fit_to_window(self) -> None:
        if self._pixmap_item.pixmap().isNull():
            return
        self.resetTransform()
        self.fitInView(
            self._pixmap_item.boundingRect(),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        if self.transform().m11() > MAX_ZOOM:
            self.resetTransform()
            self.scale(MAX_ZOOM, MAX_ZOOM)
            self.centerOn(self._pixmap_item)
        self._fit_mode = True
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def request_fit(self) -> None:
        self.fit_to_window()
        self.fit_requested.emit()

    def actual_size(self) -> None:
        if self._pixmap_item.pixmap().isNull():
            return
        self.resetTransform()
        self.centerOn(self._pixmap_item)
        self._fit_mode = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.actual_size_requested.emit()

    def toggle_fit_actual(self) -> None:
        if self._fit_mode:
            self.actual_size()
        else:
            self.request_fit()

    def zoom_in(self) -> None:
        self._zoom_by(ZOOM_STEP)

    def zoom_out(self) -> None:
        self._zoom_by(1.0 / ZOOM_STEP)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if self._pixmap_item.pixmap().isNull():
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        self._zoom_by(ZOOM_STEP if delta > 0 else 1.0 / ZOOM_STEP)
        event.accept()

    def replace_pixmap_preserving_zoom(self, pixmap: QPixmap) -> None:
        old_pixmap = self._pixmap_item.pixmap()
        if old_pixmap.isNull() or pixmap.isNull():
            self.set_pixmap(pixmap)
            return
        center = self.mapToScene(self.viewport().rect().center())
        normalized_x = center.x() / max(1, old_pixmap.width())
        normalized_y = center.y() / max(1, old_pixmap.height())
        old_scale = self.transform().m11()
        resolution_ratio = pixmap.width() / max(1, old_pixmap.width())

        self._pixmap_item.setPixmap(pixmap)
        self._sync_scene_rect()
        self.resetTransform()
        adjusted_scale = old_scale / max(resolution_ratio, 0.001)
        self.scale(adjusted_scale, adjusted_scale)
        self.centerOn(
            normalized_x * pixmap.width(),
            normalized_y * pixmap.height(),
        )
        self._fit_mode = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._fit_mode:
            self.fit_to_window()
        self._position_message()
        self.viewport_resized.emit(self.viewport().size())

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_fit_actual()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        window = self.window()
        if (
            self._fit_mode
            and event.button() == Qt.MouseButton.LeftButton
            and not window.isFullScreen()
        ):
            self._window_drag_offset = event.globalPosition().toPoint() - window.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            self._window_drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.window().move(event.globalPosition().toPoint() - self._window_drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._window_drag_offset = None
        super().mouseReleaseEvent(event)

    def _zoom_by(self, factor: float) -> None:
        if self._pixmap_item.pixmap().isNull():
            return
        current_scale = self.transform().m11()
        target_scale = current_scale * factor
        moving_outward = (
            factor > 1.0 and current_scale >= MAX_ZOOM
        ) or (
            factor < 1.0 and current_scale <= MIN_ZOOM
        )
        if moving_outward:
            return
        if MIN_ZOOM <= current_scale <= MAX_ZOOM:
            target_scale = min(MAX_ZOOM, max(MIN_ZOOM, target_scale))
            factor = target_scale / current_scale
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.scale(factor, factor)
        self._fit_mode = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        if factor > 1.0:
            self.zoom_resolution_requested.emit()

    def _update_movie_frame(self, _frame_number: int | None = None) -> None:
        if self._movie is None:
            return
        pixmap = self._movie.currentPixmap()
        if pixmap.isNull():
            return
        frame_size_changed = pixmap.size() != self._movie_frame_size
        self._movie_frame_size = pixmap.size()
        self._pixmap_item.setPixmap(pixmap)
        self._sync_scene_rect()
        if self._fit_mode and frame_size_changed:
            self.fit_to_window()

    def _detach_movie(self) -> None:
        if self._movie is None:
            return
        try:
            self._movie.frameChanged.disconnect(self._update_movie_frame)
        except (RuntimeError, TypeError):
            pass
        self._movie = None
        self._movie_frame_size = QSize()

    def _sync_scene_rect(self) -> None:
        self._scene.setSceneRect(self._pixmap_item.boundingRect())

    def _position_message(self) -> None:
        if not self._message_item.isVisible():
            return
        text_rect = self._message_item.boundingRect()
        center = self.mapToScene(self.viewport().rect().center())
        self._message_item.setPos(
            center.x() - text_rect.width() / 2,
            center.y() - text_rect.height() / 2,
        )
