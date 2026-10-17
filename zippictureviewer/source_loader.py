from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .archive_metadata import MetadataEncoding, ScanOptions
from .folder_context import FolderContext
from .models import ImageEntry, ScanResult
from .scan_worker import ScanCoordinator
from .session_store import SessionStore
from .viewer_controller import ViewerController


class SourceLoader(QObject):
    """Apply asynchronous scans transactionally and own archive-name policy."""

    status_changed = Signal(str)
    scanning_changed = Signal(bool)
    before_apply = Signal()
    # (context, result): a source is shown, from a preview or a full scan.
    source_applied = Signal(object, object)
    # (context, result): a previewed source received its complete list while
    # the shown image stayed the same.
    source_completed = Signal(object, object)
    source_rejected = Signal(str)

    def __init__(
        self,
        controller: ViewerController,
        session_store: SessionStore,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.session_store = session_store
        self.scanner = ScanCoordinator(parent=self)
        self._source_encodings: dict[str, MetadataEncoding] = {}
        self._encoding_overrides: dict[Path, MetadataEncoding] = {}
        self._focus_archive: Path | None = None
        self._previewed_generation: int | None = None
        self._shutting_down = False
        self.scanner.progress.connect(self._scan_progress)
        self.scanner.preview.connect(self._scan_preview)
        self.scanner.finished.connect(self._scan_finished)
        self.scanner.failed.connect(self._scan_failed)

    def load(
        self,
        source: Path | FolderContext,
        focus_archive: Path | None = None,
    ) -> bool:
        """Start scanning ``source``.

        ``focus_archive`` names a container inside a folder source whose first
        image should be shown, unless the saved position is already inside it.
        It is replaced by every call, so it always belongs to the latest scan.
        """

        context = (
            source
            if isinstance(source, FolderContext)
            else FolderContext.from_path(source)
        )
        generation = self.controller.begin_load(context)
        self._previewed_generation = None
        self._focus_archive = (
            _focus_access_path(context, focus_archive)
            if focus_archive is not None
            else None
        )
        if not context.is_accessible:
            self.scanner.cancel_except(generation)
            self.controller.reject_load(generation)
            self.scanning_changed.emit(False)
            self.source_rejected.emit(f"열 수 없는 경로: {context.logical_path}")
            return False

        options = ScanOptions(
            metadata_encoding=self.root_encoding(context),
            encoding_overrides=self._encoding_overrides,
            # Preview the chosen archive, or where the reader left off.
            priority_container=self._focus_archive
            or self.session_store.saved_container(context),
        )
        self.scanning_changed.emit(True)
        self.status_changed.emit("스캔 중…")
        self.scanner.start(context.access_path, generation, options)
        return True

    def cancel_current(self) -> bool:
        generation = self.controller.load_generation
        was_pending = self.scanner.pending_generation == generation
        cancelled = self.scanner.cancel(generation)
        if cancelled and not was_pending:
            self.status_changed.emit("스캔 취소 요청됨…")
        return cancelled

    def begin_shutdown(self) -> None:
        self._shutting_down = True
        self.scanner.cancel_all()

    def encoding_for(
        self,
        context: FolderContext,
        entry: ImageEntry | None = None,
    ) -> MetadataEncoding:
        if entry is not None and entry.is_archive_member:
            return self._encoding_overrides.get(
                entry.archive_path,
                self.root_encoding(context),
            )
        return self.root_encoding(context)

    def root_encoding(self, context: FolderContext) -> MetadataEncoding:
        return self._source_encodings.get(context.session_key, "auto")

    def change_encoding(self, encoding: MetadataEncoding) -> bool:
        context = self.controller.current_context
        if context is None:
            return False
        entry = self.controller.state.current_entry
        if entry is not None and entry.is_archive_member:
            self._encoding_overrides[entry.archive_path] = encoding
        else:
            self._source_encodings[context.session_key] = encoding
        return self.load(context)

    def _scan_progress(self, generation: int, path: str, count: int) -> None:
        if generation != self.controller.load_generation:
            return
        self.status_changed.emit(f"스캔 중… {count}  {Path(path).name}")

    def _scan_preview(self, generation: int, entries: list[ImageEntry]) -> None:
        context = self.controller.pending_context
        if (
            self._shutting_down
            or context is None
            or generation != self.controller.load_generation
        ):
            return
        index = self._initial_index(context, entries)
        if self.controller.apply_preview(generation, entries, index):
            self._previewed_generation = generation
            self.source_applied.emit(
                context,
                ScanResult(entries=list(entries), generation=generation),
            )

    def _scan_finished(self, generation: int, result: ScanResult) -> None:
        if self._shutting_down:
            self.controller.reject_load(generation)
            return
        context = self.controller.pending_context
        if context is None or generation != self.controller.load_generation:
            return

        self.scanning_changed.emit(False)
        if _root_load_failed(context, result):
            self.controller.reject_load(generation)
            self.source_rejected.emit(
                f"원본을 더 이상 열 수 없습니다: {context.logical_path}"
            )
            return
        if result.cancelled:
            self.controller.reject_load(generation)
            self.source_rejected.emit("스캔 취소됨")
            return

        self.before_apply.emit()
        shown = (
            self.controller.state.current_entry
            if self._previewed_generation == generation
            else None
        )
        self._previewed_generation = None
        keep_display = shown is not None and shown in result.entries
        if keep_display:
            index = result.entries.index(shown)
        else:
            index = self._initial_index(context, result.entries)
        if not self.controller.apply_load(
            generation,
            result.entries,
            result.issues,
            index,
            keep_display=keep_display,
        ):
            return
        self.session_store.save_root(context)
        if keep_display:
            self.source_completed.emit(context, result)
        else:
            self.source_applied.emit(context, result)

    def _scan_failed(self, generation: int, message: str) -> None:
        if self._shutting_down:
            self.controller.reject_load(generation)
            return
        if not self.controller.reject_load(generation):
            return
        self.scanning_changed.emit(False)
        self.source_rejected.emit(f"스캔 실패: {message}")


    def _initial_index(
        self,
        context: FolderContext,
        entries: list[ImageEntry],
    ) -> int:
        restored_index = self.session_store.restore_index(context, entries)
        focus_path = self._focus_archive
        self._focus_archive = None
        if focus_path is None:
            return restored_index

        if (
            0 <= restored_index < len(entries)
            and entries[restored_index].archive_path == focus_path
        ):
            return restored_index
        for index, entry in enumerate(entries):
            if entry.archive_path == focus_path:
                return index
        # The chosen archive yielded no images (corrupt, empty or encrypted);
        # its scan issue is reported, so keep the normal restored position.
        return restored_index


def _focus_access_path(context: FolderContext, focus_archive: Path) -> Path:
    # The scanner walks ``access_path``, so entries name containers under the
    # resolved root. Rebase the focus the same way to allow exact comparison.
    return context.access_path / Path(focus_archive).relative_to(
        context.logical_path
    )


def _root_load_failed(context: FolderContext, result: ScanResult) -> bool:
    if not context.is_accessible:
        return True
    return any(
        issue.stage == "discover" and issue.target_path == context.access_path
        for issue in result.issues
    )
