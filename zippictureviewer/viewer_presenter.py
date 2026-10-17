from __future__ import annotations

from PySide6.QtCore import QObject, QSize, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QWidget

from .archive_access import ArchiveAccess, ArchiveAccessDecision
from .decode_worker import AsyncDecoder, DecodedPayload
from .image_cache import ImageCache
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
        self.cache = ImageCache()
        self.decoder = AsyncDecoder(parent=self)
        self.current_pixmap: QPixmap | None = None
        self.current_movie: MovieResource | None = None
        self._movie_token: DisplayToken | None = None
        self.errors: dict[ImageEntry, str] = {}
        self._preload_pending: set[tuple[int, ImageEntry]] = set()
        self._last_preload_index: int | None = None
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
        self.image_view.zoom_changed.connect(self._zoom_changed)
        self.image_view.movie_failed.connect(self._movie_failed)

    def show_current(self) -> None:
        if self._closing:
            return
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

        access = self._validated_archive_access(token)
        if access is None:
            return
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
            self._closing
            or entry is None
            or entry.is_animated
            or self._full_resolution_current == entry
        ):
            return
        self._resize_timer.stop()
        self._zoom_timer.stop()
        token = self.controller.begin_display()
        if token is None:
            return
        self.decoder.clear_queued()
        self._preload_pending.clear()
        access = self._validated_archive_access(token)
        if access is None:
            return
        if not access.allowed:
            if access.error_message is not None:
                self._decode_failed(
                    token,
                    access.error_message,
                    False,
                    True,
                )
            return
        self.status_changed.emit("원본 해상도 불러오는 중…")
        self.decoder.request(
            token,
            password=access.password,
        )

    def reset_source(self) -> None:
        self.decoder.clear_queued()
        self._resize_timer.stop()
        self._zoom_timer.stop()
        self.stop_movie()
        self.current_pixmap = None
        self._full_resolution_current = None
        self.cache.clear()
        self.errors.clear()
        self._preload_pending.clear()
        self._last_preload_index = None
        self.errors_changed.emit()

    def begin_shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._resize_timer.stop()
        self._zoom_timer.stop()
        self.controller.invalidate_display()
        self.decoder.clear_queued()
        self._preload_pending.clear()
        self.stop_movie()

    def wait_for_done(self, timeout_ms: int = 0) -> bool:
        return self.decoder.wait_for_done(timeout_ms)

    def stop_movie(self) -> None:
        if self.current_movie is None:
            self._movie_token = None
            return
        self.current_movie.movie.stop()
        self.current_movie = None
        self._movie_token = None

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
                self._movie_token = token
                self._clear_error(token.entry)
                self.image_view.set_movie(self.current_movie.movie)
                if self.current_movie is None:
                    return
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
        invalid_password: bool = False,
        resource_limit: bool = False,
    ) -> None:
        if self._closing:
            return
        if preload:
            self._preload_pending.discard((token.generation, token.entry))
            return
        if not self.controller.is_current_display(token):
            return
        if invalid_password:
            self.archive_access.invalidate_password(token.entry)
            message = f"{message}\n다시 열면 ZIP 암호를 재입력할 수 있습니다."
        if (full_resolution or preserve_existing) and self.current_pixmap is not None:
            self._full_resolution_current = None
            resolution_kind = "원본" if full_resolution else "확대"
            self.errors[token.entry] = f"{resolution_kind} 해상도: {message}"
            if full_resolution:
                self.image_view.fit_to_window()
            suffix = "자원 한도" if resource_limit else f"{resolution_kind} 제한"
            self.status_changed.emit(f"{self.state.position_label}  ·  {suffix}")
            self.errors_changed.emit()
            return
        status_kind = "자원 한도" if resource_limit else "오류"
        self._show_decode_error(token, message, status_kind=status_kind)

    def _accept_preload(
        self,
        token: DisplayToken,
        payload: DecodedPayload,
    ) -> None:
        self._preload_pending.discard((token.generation, token.entry))
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

    def _show_decode_error(
        self,
        token: DisplayToken,
        message: str,
        *,
        status_kind: str = "오류",
    ) -> None:
        if self._closing or not self.controller.is_current_display(token):
            return
        self.stop_movie()
        self.current_pixmap = None
        self.errors[token.entry] = message
        self.image_view.show_message(
            f"이미지를 열 수 없습니다\n{token.entry.image_label}\n{message}"
        )
        self.status_changed.emit(f"{self.state.position_label}  ·  {status_kind}")
        self.errors_changed.emit()

    def _movie_failed(self, message: str) -> None:
        token = self._movie_token
        if token is None or not self.controller.is_current_display(token):
            return
        self._show_decode_error(token, f"GIF 재생 오류: {message}")

    def _schedule_preload(self, token: DisplayToken) -> None:
        current_index = self.state.current_index
        direction = 1
        if self._last_preload_index is not None and current_index < self._last_preload_index:
            direction = -1
        self._last_preload_index = current_index
        offsets = (1, 2, 3, -1, -2) if direction > 0 else (-1, -2, -3, 1, 2)
        for offset in offsets:
            index = current_index + offset
            if not 0 <= index < len(self.state.entries):
                continue
            entry = self.state.entries[index]
            if not self._should_preload(entry, token.entry, token.generation):
                continue
            password = self.archive_access.cached_password(entry)
            self._preload_pending.add((token.generation, entry))
            self.decoder.request(
                DisplayToken(token.generation, entry),
                preload=True,
                password=password,
                scaled_size=self._fit_decode_size(),
            )

    def _should_preload(
        self,
        entry: ImageEntry,
        current_entry: ImageEntry,
        generation: int,
    ) -> bool:
        if entry == current_entry or entry.is_animated:
            return False
        if (generation, entry) in self._preload_pending:
            return False
        if (
            entry.encryption is not None
            and self.archive_access.cached_password(entry) is None
        ):
            return False
        return self.cache.get_image(entry) is None

    def _fit_requested(self) -> None:
        self._zoom_timer.stop()
        self._resize_timer.stop()
        if self._closing or self.current_pixmap is None:
            return
        self.controller.invalidate_display()
        self.decoder.clear_queued()
        self._preload_pending.clear()
        self._refresh_fit_preview()

    def _viewport_resized(self, _size: QSize) -> None:
        if self.image_view.fit_mode:
            self._resize_timer.start()

    def _zoom_changed(self, request_higher_resolution: bool) -> None:
        entry = self.state.current_entry
        if (
            self._closing
            or entry is None
            or entry.is_animated
            or self._full_resolution_current == entry
        ):
            return
        self._resize_timer.stop()
        self._zoom_timer.stop()
        self.controller.invalidate_display()
        self.decoder.clear_queued()
        self._preload_pending.clear()
        if request_higher_resolution:
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
        requested_size = self._zoom_decode_size(pixmap)
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

    def _validated_archive_access(
        self,
        token: DisplayToken,
    ) -> ArchiveAccessDecision | None:
        access = self.archive_access.request(token.entry, self.dialog_parent)
        if self._closing or not self.controller.is_current_display(token):
            return None
        return access

    def _fit_decode_size(self) -> QSize:
        viewport = self.image_view.viewport()
        ratio = max(1.0, viewport.devicePixelRatioF())
        return QSize(
            max(1, int(viewport.width() * ratio)),
            max(1, int(viewport.height() * ratio)),
        )

    def _zoom_decode_size(self, pixmap: QPixmap) -> QSize:
        ratio = max(1.0, self.image_view.viewport().devicePixelRatioF())
        scale = max(1.0, self.image_view.transform().m11())
        headroom = 1.1
        return QSize(
            max(1, int(pixmap.width() * scale * ratio * headroom)),
            max(1, int(pixmap.height() * scale * ratio * headroom)),
        )
