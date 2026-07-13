from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

from .folder_context import FolderContext
from .models import ImageEntry
from .session_store import SessionStore
from .viewer_state import ViewerState


class PositionSaver(QObject):
    """Debounce position fsyncs so rapid navigation never blocks each frame."""

    def __init__(
        self,
        session_store: SessionStore,
        delay_ms: int = 200,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.session_store = session_store
        self._pending: tuple[FolderContext, ImageEntry, int, int] | None = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(delay_ms)
        self.timer.timeout.connect(self.flush)

    def schedule(self, context: FolderContext, state: ViewerState) -> None:
        entry = state.current_entry
        if entry is None:
            return
        global_index = state.current_index
        container_index = sum(
            candidate.archive_path == entry.archive_path
            for candidate in state.entries[:global_index]
        )
        self._pending = (
            context,
            entry,
            global_index,
            container_index,
        )
        self.timer.start()

    def flush(self) -> None:
        pending = self._pending
        if pending is None:
            return
        self._pending = None
        self.timer.stop()
        context, entry, global_index, container_index = pending
        self.session_store.save_position(
            context,
            entry,
            global_index,
            container_index=container_index,
        )
