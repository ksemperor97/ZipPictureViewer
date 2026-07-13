from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
)

from .folder_context import ARCHIVE_EXTENSIONS, FolderContext
from .folder_navigation import sibling_context
from .image_view import ImageView
from .mac_presentation import set_menu_bar_auto_hidden
from .models import ImageEntry, ScanIssue, ScanResult
from .position_saver import PositionSaver
from .session_store import SessionStore
from .source_loader import SourceLoader
from .viewer_controller import ViewerController
from .viewer_controls import ViewerControls, ViewerInfoPanel
from .viewer_presenter import ImagePresenter
from .viewer_shortcuts import install_viewer_shortcuts
from .viewer_widgets import OverlayController, ViewerSurface


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Zip Picture Viewer")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.resize(1100, 800)
        self.setMinimumSize(480, 360)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

        self.controller = ViewerController()
        self.state = self.controller.state
        self.current_root: Path | None = None
        self.session_store = SessionStore()
        self.source_loader = SourceLoader(
            self.controller,
            self.session_store,
            parent=self,
        )
        self.scanner = self.source_loader.scanner
        self._closing = False
        self.position_saver = PositionSaver(self.session_store, parent=self)

        self.image_view = ImageView()
        self.presenter = ImagePresenter(self.controller, self.image_view, self)
        # Compatibility aliases for integrations using the original fields.
        self.image_cache = self.presenter.cache
        self.decoder = self.presenter.decoder
        # Compatibility alias for integrations that used MainWindow.image_label.
        self.image_label = self.image_view
        self.controls_panel = ViewerControls()
        self.info_panel = ViewerInfoPanel()
        for name in self.controls_panel.button_names:
            setattr(self, name, getattr(self.controls_panel, name))
        self.status_label = self.controls_panel.status_label
        self.encoding_combo = self.controls_panel.encoding_combo
        self.file_label = self.info_panel.file_label
        self.file_label.setToolTip("")
        self._close_poll_timer = QTimer(self)
        self._close_poll_timer.setInterval(50)
        self._close_poll_timer.timeout.connect(self._finish_close_when_idle)
        self._restore_timer = QTimer(self)
        self._restore_timer.setSingleShot(True)
        self._restore_timer.timeout.connect(self._restore_last_source)
        self._focus_timer = QTimer(self)
        self._focus_timer.setSingleShot(True)
        self._focus_timer.timeout.connect(self.image_view.setFocus)

        self.viewer_surface = ViewerSurface(
            self.image_view,
            self.controls_panel,
            self.info_panel,
        )
        self.setCentralWidget(self.viewer_surface)
        self.overlays = OverlayController(
            self.viewer_surface,
            self.isFullScreen,
            parent=self,
        )
        self.overlay_hide_timer = self.overlays.timer
        self._connect_actions()
        self._update_navigation()
        self.overlays.set_visible(False)
        self.presenter.entry_started.connect(self._display_entry_started)
        self.presenter.status_changed.connect(self.status_label.setText)
        self.presenter.errors_changed.connect(self._display_errors_changed)
        self.source_loader.status_changed.connect(self._source_status_changed)
        self.source_loader.scanning_changed.connect(
            self.controls_panel.set_scanning
        )
        self.source_loader.before_apply.connect(self.position_saver.flush)
        self.source_loader.source_applied.connect(self._source_applied)
        self.source_loader.source_rejected.connect(self._source_rejected)
        QApplication.instance().installEventFilter(self)
        self._restore_timer.start(0)
        self._focus_timer.start(0)

    @property
    def current_context(self) -> FolderContext | None:
        return self.controller.current_context

    @property
    def current_pixmap(self):
        return self.presenter.current_pixmap

    @property
    def current_movie(self):
        return self.presenter.current_movie

    def open_folder(self) -> None:
        if self._closing:
            return
        selected = QFileDialog.getExistingDirectory(self, "이미지 컬렉션 폴더 선택")
        if selected:
            self.load_source(Path(selected))

    def open_archive(self) -> None:
        if self._closing:
            return
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "ZIP/CBZ 선택",
            "",
            "ZIP archives (*.zip *.cbz)",
        )
        if selected:
            self.load_source(Path(selected))

    def load_folder(self, root: Path) -> None:
        """Compatibility alias for callers that load directory roots."""

        self.load_source(root)

    def load_source(self, source: Path | FolderContext) -> None:
        if self._closing:
            return
        context = (
            source
            if isinstance(source, FolderContext)
            else FolderContext.from_path(source)
        )
        selected_entry = (
            self.state.current_entry if context == self.current_context else None
        )
        self._select_encoding_for(context, selected_entry)
        self.source_loader.session_store = self.session_store
        if self.source_loader.load(context):
            self.overlays.show_temporarily()

    def refresh_source(self) -> None:
        if self._closing:
            return
        if self.current_context is not None:
            self.load_source(self.current_context)

    def cancel_scan(self) -> None:
        if self.source_loader.cancel_current():
            self.cancel_scan_button.setEnabled(False)
            self.overlays.show_temporarily()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._closing:
            event.ignore()
            return
        if self._dropped_source(event.mimeData()) is None:
            event.ignore()
            return
        event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        if self._closing:
            event.ignore()
            return
        source = self._dropped_source(event.mimeData())
        if source is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self.load_source(source)

    def show_current_image(self) -> None:
        if self._closing:
            return
        self.presenter.show_current()

    def show_next_image(self) -> None:
        if self._closing:
            return
        if self.state.move_next():
            self.show_current_image()

    def show_previous_image(self) -> None:
        if self._closing:
            return
        if self.state.move_previous():
            self.show_current_image()

    def show_next_archive(self) -> None:
        if self._closing:
            return
        if self.state.move_next_archive():
            self.show_current_image()

    def show_previous_archive(self) -> None:
        if self._closing:
            return
        if self.state.move_previous_archive():
            self.show_current_image()

    def open_next_sibling_folder(self) -> None:
        if self._closing:
            return
        self._open_sibling_source(1)

    def open_previous_sibling_folder(self) -> None:
        if self._closing:
            return
        self._open_sibling_source(-1)

    def show_issues(self) -> None:
        messages = self._issue_messages()
        if not messages:
            return
        QMessageBox.information(
            self,
            "읽지 못한 항목",
            "\n\n".join(messages[:30]),
        )

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
            return
        self.showFullScreen()
        self._sync_window_state()

    def exit_fullscreen(self) -> None:
        if not self.isFullScreen():
            self._sync_window_state()
            return
        self.showNormal()
        self._sync_window_state()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._closing = True
        self.setAcceptDrops(False)
        self.controls_panel.setEnabled(False)
        self.image_view.setEnabled(False)
        self._restore_timer.stop()
        self._focus_timer.stop()
        self.overlays.stop()
        self.source_loader.begin_shutdown()
        self.presenter.begin_shutdown()
        if self.scanner.active_count or not self.presenter.wait_for_done(0):
            event.ignore()
            self.status_label.setText("작업 종료 중…")
            self.overlays.set_visible(True)
            self._close_poll_timer.start()
            return

        self._close_poll_timer.stop()
        self.position_saver.flush()
        set_menu_bar_auto_hidden(False)
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if not self._closing and event.type() == QEvent.Type.MouseMove:
            self.overlays.show_temporarily()
        return super().eventFilter(watched, event)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0, self._sync_window_state)

    def _sync_window_state(self) -> None:
        fullscreen = self.isFullScreen()
        set_menu_bar_auto_hidden(fullscreen)
        self.fullscreen_button.setText("창모드" if fullscreen else "전체화면")
        self.overlays.sync_grip()

    def _connect_actions(self) -> None:
        self.open_button.clicked.connect(self.open_folder)
        self.open_archive_button.clicked.connect(self.open_archive)
        self.previous_folder_button.clicked.connect(self.open_previous_sibling_folder)
        self.next_folder_button.clicked.connect(self.open_next_sibling_folder)
        self.refresh_button.clicked.connect(self.refresh_source)
        self.cancel_scan_button.clicked.connect(self.cancel_scan)
        self.previous_archive_button.clicked.connect(self.show_previous_archive)
        self.next_archive_button.clicked.connect(self.show_next_archive)
        self.previous_button.clicked.connect(self.show_previous_image)
        self.next_button.clicked.connect(self.show_next_image)
        self.fit_button.clicked.connect(self.image_view.request_fit)
        self.actual_size_button.clicked.connect(self.image_view.actual_size)
        self.zoom_out_button.clicked.connect(self.image_view.zoom_out)
        self.zoom_in_button.clicked.connect(self.image_view.zoom_in)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.minimize_button.clicked.connect(self.showMinimized)
        self.close_button.clicked.connect(self.close)
        self.issues_button.clicked.connect(self.show_issues)
        self.encoding_combo.currentIndexChanged.connect(self._encoding_changed)
        self._shortcuts = install_viewer_shortcuts(self)

    def _source_applied(
        self,
        context: FolderContext,
        result: ScanResult,
    ) -> None:
        self.current_root = context.logical_path
        self.presenter.reset_source()
        self._update_issues_button()

        if not result.entries:
            if result.issues:
                message = "이미지 컨테이너를 읽지 못했습니다"
            elif result.discovered_files == 0:
                message = "빈 폴더입니다"
            else:
                message = "지원되는 이미지 형식이 없습니다"
            self.image_view.show_message(message)
            self.file_label.setText(str(context.logical_path))
            self.file_label.setToolTip(str(context.logical_path))
            self.status_label.setText("0 / 0")
            self._update_navigation()
            return

        self.show_current_image()

    def _source_status_changed(self, message: str) -> None:
        self.status_label.setText(message)

    def _source_rejected(self, message: str) -> None:
        self._show_transient_status(message)
        self._update_navigation()

    def _display_entry_started(self, entry: ImageEntry) -> None:
        context = self.current_context
        if context is not None:
            self._select_encoding_for(context, entry)
        self._update_entry_metadata(entry)
        self._update_navigation()
        self._save_position()

    def _display_errors_changed(self) -> None:
        self._update_navigation()
        self._update_issues_button()
        if self.presenter.errors:
            self.overlays.show_temporarily()

    def _update_entry_metadata(self, entry: ImageEntry) -> None:
        text = f"{entry.archive_path}  |  {entry.member_name}"
        self.file_label.setText(text)
        self.file_label.setToolTip(text)
        self.status_label.setText(self.state.position_label)

    def _save_position(self) -> None:
        context = self.current_context
        if context is None:
            return
        self.position_saver.session_store = self.session_store
        self.position_saver.schedule(context, self.state)

    def _restore_last_source(self) -> None:
        if (
            self._closing
            or self.current_context is not None
            or self.controller.pending_context is not None
        ):
            return
        context = self.session_store.last_context()
        if context is not None:
            self.load_source(context)

    def _open_sibling_source(self, step: int) -> None:
        if self._closing:
            return
        context = self.current_context
        if context is None:
            return
        sibling = sibling_context(context, step)
        if sibling is None:
            self._show_transient_status("형제 항목을 찾지 못했습니다")
            return
        self.load_source(sibling)

    def _update_navigation(self) -> None:
        has_entries = self.state.has_entries
        has_source = self.current_context is not None
        self.previous_folder_button.setEnabled(has_source)
        self.next_folder_button.setEnabled(has_source)
        self.refresh_button.setEnabled(has_source)
        self.previous_archive_button.setEnabled(
            has_entries and self.state.has_previous_archive()
        )
        self.next_archive_button.setEnabled(has_entries and self.state.has_next_archive())
        self.previous_button.setEnabled(has_entries and self.state.current_index > 0)
        self.next_button.setEnabled(has_entries)
        for button in (
            self.fit_button,
            self.actual_size_button,
            self.zoom_out_button,
            self.zoom_in_button,
        ):
            button.setEnabled(has_entries)

    def _update_issues_button(self) -> None:
        count = len(self.controller.scan_issues) + len(self.presenter.errors)
        self.controls_panel.set_issue_count(count)

    def _issue_messages(self) -> list[str]:
        messages = [
            f"[{issue.error_kind}] {issue.target_path}\n{issue.message}"
            for issue in self.controller.scan_issues
            if isinstance(issue, ScanIssue)
        ]
        messages.extend(self.presenter.issue_messages())
        return messages

    def _select_encoding_for(
        self,
        context: FolderContext,
        entry: ImageEntry | None = None,
    ) -> None:
        encoding = self.source_loader.encoding_for(context, entry)
        index = self.encoding_combo.findData(encoding)
        if index < 0:
            return
        blocked = self.encoding_combo.blockSignals(True)
        self.encoding_combo.setCurrentIndex(index)
        self.encoding_combo.blockSignals(blocked)

    def _encoding_changed(self) -> None:
        if self._closing:
            return
        encoding = self.encoding_combo.currentData()
        if encoding not in ("auto", "cp437", "cp949"):
            return
        if self.source_loader.change_encoding(encoding):
            self.overlays.show_temporarily()

    def _finish_close_when_idle(self) -> None:
        if self.scanner.active_count or not self.presenter.wait_for_done(0):
            return
        self._close_poll_timer.stop()
        self.close()

    def _dropped_source(self, mime_data) -> Path | None:
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

    def _show_transient_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.overlays.show_temporarily()

    def _show_overlays_temporarily(self) -> None:
        self.overlays.show_temporarily()

    def _set_overlays_visible(self, visible: bool) -> None:
        self.overlays.set_visible(visible)

    def _sync_resize_grip(self, visible: bool | None = None) -> None:
        self.overlays.sync_grip(visible)
