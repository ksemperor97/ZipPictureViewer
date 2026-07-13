from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, QSize, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage

from .image_loader import (
    SourceChangedError,
    current_source_revision,
    load_image,
    read_image_bytes,
)
from .models import ContainerRevision, ImageEntry
from .viewer_controller import DisplayToken


@dataclass(frozen=True)
class DecodedPayload:
    image: QImage | None = None
    animation_bytes: bytes | None = None
    source_revision: ContainerRevision | None = None
    full_resolution: bool = False
    preserve_zoom: bool = False


class DecodeSignals(QObject):
    ready = Signal(object, object, bool)
    failed = Signal(object, str, bool, bool, bool)


class DecodeTask(QRunnable):
    def __init__(
        self,
        token: DisplayToken,
        *,
        preload: bool,
        password: bytes | None,
        scaled_size: QSize | None,
        preserve_zoom: bool,
        signals: DecodeSignals,
    ) -> None:
        super().__init__()
        self.token = token
        self.preload = preload
        self.password = password
        self.scaled_size = QSize(scaled_size) if scaled_size is not None else None
        self.preserve_zoom = preserve_zoom
        self.signals = signals

    @Slot()
    def run(self) -> None:
        try:
            payload = self._decode(self.token.entry)
        except Exception as error:
            full_resolution = self.scaled_size is None and not self.token.entry.is_animated
            self.signals.failed.emit(
                self.token,
                str(error),
                self.preload,
                full_resolution,
                self.preserve_zoom,
            )
            return
        self.signals.ready.emit(self.token, payload, self.preload)

    def _decode(self, entry: ImageEntry) -> DecodedPayload:
        observed_revision = current_source_revision(entry)
        if (
            entry.source_revision is not None
            and observed_revision != entry.source_revision
        ):
            raise SourceChangedError(
                f"Source changed before decode: {entry.source_path}"
            )
        if entry.is_animated:
            animation_bytes = read_image_bytes(entry, password=self.password)
            payload = DecodedPayload(
                animation_bytes=animation_bytes,
                source_revision=observed_revision,
            )
        else:
            image = load_image(
                entry,
                password=self.password,
                scaled_size=self.scaled_size,
            )
            payload = DecodedPayload(
                image=image,
                source_revision=observed_revision,
                full_resolution=self.scaled_size is None,
                preserve_zoom=self.preserve_zoom,
            )
        if current_source_revision(entry) != observed_revision:
            raise SourceChangedError(
                f"Source changed while decoding: {entry.source_path}"
            )
        return payload


class AsyncDecoder(QObject):
    ready = Signal(object, object, bool)
    failed = Signal(object, str, bool, bool, bool)

    def __init__(self, max_threads: int = 2, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._preview_pool = QThreadPool(self)
        self._preview_pool.setMaxThreadCount(2)
        self._full_resolution_pool = QThreadPool(self)
        self._full_resolution_pool.setMaxThreadCount(1)
        self._preload_pool = QThreadPool(self)
        self._preload_pool.setMaxThreadCount(max(1, max_threads - 1))
        self._signals = DecodeSignals()
        self._signals.ready.connect(self.ready)
        self._signals.failed.connect(self.failed)

    def request(
        self,
        token: DisplayToken,
        *,
        preload: bool = False,
        password: bytes | None = None,
        scaled_size: QSize | None = None,
        preserve_zoom: bool = False,
    ) -> None:
        task = DecodeTask(
            token,
            preload=preload,
            password=password,
            scaled_size=scaled_size,
            preserve_zoom=preserve_zoom,
            signals=self._signals,
        )
        if preload:
            pool = self._preload_pool
        elif scaled_size is None and not token.entry.is_animated:
            pool = self._full_resolution_pool
        else:
            pool = self._preview_pool
        pool.start(task)

    def clear_queued(self) -> None:
        self._preview_pool.clear()
        self._full_resolution_pool.clear()
        self._preload_pool.clear()

    def wait_for_done(self, timeout_ms: int = 0) -> bool:
        preview_done = self._preview_pool.waitForDone(timeout_ms)
        full_resolution_done = self._full_resolution_pool.waitForDone(timeout_ms)
        preload_done = self._preload_pool.waitForDone(timeout_ms)
        return preview_done and full_resolution_done and preload_done
