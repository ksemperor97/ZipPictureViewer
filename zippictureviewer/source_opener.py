from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QObject, QTimer, Signal
from PySide6.QtWidgets import QFileDialog, QWidget

from .archive_metadata import MetadataEncoding
from .folder_context import FolderContext
from .folder_navigation import containing_folder_context, sibling_context
from .formats import ARCHIVE_EXTENSIONS
from .session_store import SessionStore
from .source_loader import SourceLoader
from .viewer_controller import ViewerController


class SourceOpener(QObject):
    """Turn user requests (dialogs, drops, Finder, restore) into source loads."""

    # (context, entry to keep selected) just before a load starts.
    about_to_load = Signal(object, object)
    # A load was started; the window reveals its controls.
    load_started = Signal()
    # A short message for the status label.
    message = Signal(str)

    def __init__(
        self,
        dialog_parent: QWidget,
        controller: ViewerController,
        source_loader: SourceLoader,
        session_store: SessionStore,
    ) -> None:
        super().__init__(dialog_parent)
        self._dialog_parent = dialog_parent
        self._controller = controller
        self._source_loader = source_loader
        self._session_store = session_store
        self._shutting_down = False
        self._restore_timer = QTimer(self)
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self._restore_last_source)

    def schedule_restore(self) -> None:
        self._restore_timer.start(0)

    def begin_shutdown(self) -> None:
        self._shutting_down = True
        self._restore_timer.stop()

    def choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self._dialog_parent,
            "이미지 컬렉션 폴더 선택",
        )
        if selected:
            self.open_path(Path(selected))

    def choose_archive(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self._dialog_parent,
            "ZIP/CBZ 선택",
            "",
            "ZIP archives (*.zip *.cbz)",
        )
        if selected:
            self.open_path(Path(selected))

    def open_path(self, path: Path) -> None:
        """Open a user-chosen folder or archive.

        A chosen archive opens its containing folder so sibling archives stay
        reachable, starting at the chosen archive. ``load`` keeps the
        exact-source semantics used by session restore and sibling navigation.
        """

        # An explicit request supersedes restoring the previous session.
        self._restore_timer.stop()
        context = FolderContext.from_path(path)
        folder_context = containing_folder_context(context)
        if folder_context is None:
            self.load(context)
            return
        self.load(folder_context, focus_archive=context.logical_path)

    def load(self, context: FolderContext, focus_archive: Path | None = None) -> None:
        if self._shutting_down:
            return
        selected_entry = (
            self._controller.state.current_entry
            if context == self._controller.current_context
            else None
        )
        self.about_to_load.emit(context, selected_entry)
        if self._source_loader.load(context, focus_archive):
            self.load_started.emit()

    def refresh(self) -> None:
        context = self._controller.current_context
        if context is not None:
            self.load(context)

    def open_sibling(self, step: int) -> None:
        context = self._controller.current_context
        if context is None:
            return
        sibling = sibling_context(context, step)
        if sibling is None:
            self.message.emit("형제 항목을 찾지 못했습니다")
            return
        self.load(sibling)

    def change_encoding(self, encoding: MetadataEncoding) -> None:
        if self._shutting_down:
            return
        if self._source_loader.change_encoding(encoding):
            self.load_started.emit()

    def _restore_last_source(self) -> None:
        if (
            self._controller.current_context is not None
            or self._controller.pending_context is not None
        ):
            return
        context = self._session_store.last_context()
        if context is not None:
            self.load(context)


def dropped_source(mime_data: QMimeData) -> Path | None:
    """Return the first dropped local folder or archive."""

    if not mime_data.hasUrls():
        return None
    for url in mime_data.urls():
        if not url.isLocalFile():
            continue
        path = Path(url.toLocalFile())
        if path.is_dir() or (
            path.is_file() and path.suffix.casefold() in ARCHIVE_EXTENSIONS
        ):
            return path
    return None
