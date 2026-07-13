from __future__ import annotations

from PySide6.QtCore import QObject, QSize, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QWidget

from .archive_access import ArchiveAccess
from .decode_worker import AsyncDecoder, DecodedPayload
from .image_cache import PixmapCache
from .image_loader import (
    MovieResource,
    SourceChangedError,
    create_movie_resource,
    current_source_revision,
)
from .image_view import ImageView
from .models import ImageEntry
from .viewer_controller import DisplayToken, ViewerController


class ImagePresenter(QObject):
    """Coordinate display generations, decoding, cache, movies, and errors."""

    entry_started = Signal(object)
    status_changed = Signal(str)
    errors_changed = Signal()

    def __init__(
        self,
        controller: ViewerController,
        image_view: ImageView,
        dialog_parent: QWidget,
    ) -> None:
        super().__init__(dialog_parent)
        self.controller = controller
        self.state = controller.state
        self.image_view = image_view
        self.dialog_parent = dialog_parent
        self.cache = PixmapCache()
        self.decoder = AsyncDecoder(parent=self)
        self.current_pixmap: QPixmap | None = None
        self.current_movie: MovieResource | None = None
        self.errors: dict[ImageEntry, str] = {}
        self._preload_pending: set[ImageEntry] = set()
        self.archive_access = ArchiveAccess()
        self._full_resolution_current: ImageEntry | None = None
        self._closing = False
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._refresh_fit_preview)
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.setInterval(120)
        self._zoom_timer.timeout.connect(self._request_zoom_resolution)
        self.decoder.ready.connect(self._decoded)
        self.decoder.failed.connect(self._decode_failed)
        self.image_view.actual_size_requested.connect(
            self.request_full_resolution
        )
        self.image_view.fit_requested.connect(self._fit_requested)
        self.image_view.viewport_resized.connect(self._viewport_resized)
        self.image_view.zoom_resolution_requested.connect(
            self._zoom_resolution_requested
        )

    def show_current(self) -> None:
        token = self.controller.begin_display()
        if token is None:
            return

        self.decoder.clear_queued()
        self._preload_pending.clear()
        self._resize_timer.stop()
        self._zoom_timer.stop()
        self.stop_movie()
        self.current_pixmap = None
        self._full_resolution_current = None
        self.image_view.show_message("불러오는 중…")
        self.entry_started.emit(token.entry)

        if not token.entry.is_animated:
            cached = self.cache.get_image(token.entry)
            if cached is not None and not self._preview_is_too_small(cached):
                self._clear_error(token.entry)
                self._show_decoded_image(token, cached)
                return

        access = self.archive_access.request(token.entry, self.dialog_parent)
        if access.allowed:
            self.decoder.request(
                token,
                password=access.password,
                scaled_size=self._fit_decode_size(),
            )
        elif access.error_message is not None:
            self._show_decode_error(token, access.error_message)

    def request_full_resolution(self) -> None:
        entry = self.state.current_entry
        if (
            entry is None
            or entry.is_animated
            or self._full_resolution_current == entry
        ):
            return
        token = self.controller.begin_display()
        if token is None:
            return
        self.decoder.clear_queued()
        self._preload_pending.clear()
        self.status_changed.emit("원본 해상도 불러오는 중…")
        self.decoder.request(
            token,
            password=self.archive_access.cached_password(entry),
        )

    def reset_source(self) -> None:
        self.decoder.clear_queued()
        self.stop_movie()
        self.current_pixmap = None
        self._full_resolution_current = None
        self.cache.clear()
        self.errors.clear()
        self._preload_pending.clear()
        self.errors_changed.emit()

    def begin_shutdown(self) -> None:
        self._closing = True
        self.decoder.clear_queued()
        self.stop_movie()

    def wait_for_done(self, timeout_ms: int = 0) -> bool:
        return self.decoder.wait_for_done(timeout_ms)

    def stop_movie(self) -> None:
        if self.current_movie is None:
            return
        self.current_movie.movie.stop()
        self.current_movie = None

    def issue_messages(self) -> list[str]:
        return [
            f"[image] {entry.archive_path} | {entry.member_name}\n{message}"
            for entry, message in self.errors.items()
        ]

    def _decoded(
        self,
        token: DisplayToken,
        payload: DecodedPayload,
        preload: bool,
    ) -> None:
        if self._closing:
            return
        if preload:
            self._accept_preload(token, payload)
            return
        if not self.controller.is_current_display(token):
            return

        try:
            if payload.image is not None:
                self.cache.put_image(
                    token.entry,
                    payload.image,
                    revision=payload.source_revision,
                )
                self._show_decoded_image(
                    token,
                    payload.image,
                    actual_size=payload.full_resolution,
                    preserve_zoom=payload.preserve_zoom,
                )
            elif payload.animation_bytes is not None:
                if payload.source_revision != current_source_revision(token.entry):
                    raise SourceChangedError(
                        f"Source changed before display: {token.entry.source_path}"
                    )
                self.current_movie = create_movie_resource(
                    payload.animation_bytes,
                    token.entry.member_name,
                )
                self.image_view.set_movie(self.current_movie.movie)
                self._clear_error(token.entry)
                self._schedule_preload(token)
            else:
                raise ValueError("Decoder returned no displayable content")
        except Exception as error:
            self._show_decode_error(token, str(error))

    def _decode_failed(
        self,
        token: DisplayToken,
        message: str,
        preload: bool,
        full_resolution: bool,
        preserve_existing: bool = False,
    ) -> None:
        if self._closing:
            return
        if preload:
            self._preload_pending.discard(token.entry)
            return
        if not self.controller.is_current_display(token):
            return
        if (full_resolution or preserve_existing) and self.current_pixmap is not None:
            self._full_resolution_current = None
            resolution_kind = "원본" if full_resolution else "확대"
            self.errors[token.entry] = f"{resolution_kind} 해상도: {message}"
            if full_resolution:
                self.image_view.fit_to_window()
            self.status_changed.emit(
                f"{self.state.position_label}  ·  {resolution_kind} 제한"
            )
            self.errors_changed.emit()
            return
        if token.entry.encryption == "zipcrypto":
            self.archive_access.invalidate_password(token.entry)
            message = f"{message}\n다시 열면 ZIP 암호를 재입력할 수 있습니다."
        self._show_decode_error(token, message)

    def _accept_preload(
        self,
        token: DisplayToken,
        payload: DecodedPayload,
    ) -> None:
        self._preload_pending.discard(token.entry)
        if not self.controller.is_current_generation(token):
            return
        if payload.image is None:
            return
        try:
            self.cache.put_image(
                token.entry,
                payload.image,
                revision=payload.source_revision,
            )
        except Exception:
            return

    def _show_decoded_image(
        self,
        token: DisplayToken,
        image: QImage,
        *,
        actual_size: bool = False,
        preserve_zoom: bool = False,
    ) -> None:
        if not self.controller.is_current_display(token):
            return
        self.current_pixmap = QPixmap.fromImage(image)
        self._full_resolution_current = token.entry if actual_size else None
        self._clear_error(token.entry)
        if preserve_zoom:
            self.image_view.replace_pixmap_preserving_zoom(self.current_pixmap)
            self._schedule_preload(token)
            return
        self.image_view.set_pixmap(
            self.current_pixmap,
            reset_view=not actual_size,
        )
        if actual_size:
            self.image_view.actual_size()
            self.status_changed.emit(self.state.position_label)
        self._schedule_preload(token)

    def _show_decode_error(self, token: DisplayToken, message: str) -> None:
        self.stop_movie()
        self.current_pixmap = None
        self.errors[token.entry] = message
        self.image_view.show_message(
            f"이미지를 열 수 없습니다\n{token.entry.image_label}\n{message}"
        )
        self.status_changed.emit(f"{self.state.position_label}  ·  오류")
        self.errors_changed.emit()

    def _schedule_preload(self, token: DisplayToken) -> None:
        current_index = self.state.current_index
        start = max(0, current_index - 2)
        stop = min(len(self.state.entries), current_index + 4)
        for entry in self.state.entries[start:stop]:
            if not self._should_preload(entry, token.entry):
                continue
            password = self.archive_access.cached_password(entry)
            self._preload_pending.add(entry)
            self.decoder.request(
                DisplayToken(token.generation, entry),
                preload=True,
                password=password,
                scaled_size=self._fit_decode_size(),
            )

    def _should_preload(self, entry: ImageEntry, current_entry: ImageEntry) -> bool:
        if entry == current_entry or entry.is_animated:
            return False
        if entry in self._preload_pending:
            return False
        if (
            entry.encryption is not None
            and self.archive_access.cached_password(entry) is None
        ):
            return False
        return self.cache.get_image(entry) is None

    def _fit_requested(self) -> None:
        self._zoom_timer.stop()
        self.controller.invalidate_display()
        self.decoder.clear_queued()
        self._preload_pending.clear()
        self._refresh_fit_preview()

    def _viewport_resized(self, _size: QSize) -> None:
        if self.image_view.fit_mode:
            self._resize_timer.start()

    def _zoom_resolution_requested(self) -> None:
        entry = self.state.current_entry
        if (
            entry is None
            or entry.is_animated
            or self._full_resolution_current == entry
        ):
            return
        self._zoom_timer.start()

    def _request_zoom_resolution(self) -> None:
        entry = self.state.current_entry
        pixmap = self.current_pixmap
        if (
            self._closing
            or self.image_view.fit_mode
            or entry is None
            or pixmap is None
        ):
            return
        password = self.archive_access.cached_password(entry)
        if entry.encryption is not None and password is None:
            return
        token = self.controller.begin_display()
        if token is None:
            return
        requested_size = QSize(
            max(1, pixmap.width() * 2),
            max(1, pixmap.height() * 2),
        )
        self.decoder.request(
            token,
            password=password,
            scaled_size=requested_size,
            preserve_zoom=True,
        )

    def _refresh_fit_preview(self) -> None:
        if self._closing or not self.image_view.fit_mode:
            return
        entry = self.state.current_entry
        if entry is None or entry.is_animated or self.current_pixmap is None:
            return
        if not self._preview_is_too_small(self.current_pixmap):
            return
        password = self.archive_access.cached_password(entry)
        if entry.encryption is not None and password is None:
            return
        token = self.controller.begin_display()
        if token is None:
            return
        self.decoder.request(
            token,
            password=password,
            scaled_size=self._fit_decode_size(),
        )

    def _preview_is_too_small(self, image: QImage | QPixmap) -> bool:
        requested = self._fit_decode_size()
        return max(requested.width(), requested.height()) > int(
            max(image.width(), image.height()) * 1.25
        )

    def _clear_error(self, entry: ImageEntry) -> None:
        if self.errors.pop(entry, None) is not None:
            self.errors_changed.emit()

    def _fit_decode_size(self) -> QSize:
        viewport = self.image_view.viewport()
        ratio = max(1.0, viewport.devicePixelRatioF())
        return QSize(
            max(1, int(viewport.width() * ratio)),
            max(1, int(viewport.height() * ratio)),
        )
