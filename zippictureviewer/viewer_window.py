from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMainWindow

from .folder_context import FolderContext
from .image_view import ImageView
from .issue_dialog import IssueDialog
from .mac_presentation import set_menu_bar_auto_hidden
from .models import ImageEntry, ScanResult
from .position_saver import PositionSaver
from .session_store import SessionStore
from .shortcut_help_dialog import ShortcutHelpDialog
from .source_loader import SourceLoader
from .source_opener import SourceOpener, dropped_source
from .viewer_controller import ViewerController
from .viewer_controls import ViewerControls, ViewerInfoPanel
from .viewer_presenter import ImagePresenter
from .viewer_shortcuts import install_viewer_shortcuts
from .viewer_status import ViewerStatus
from .viewer_widgets import OverlayController, ViewerSurface


class MainWindow(QMainWindow):
    """Compose the viewer and own window-level behaviour and shutdown."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Zip Picture Viewer")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.resize(1100, 800)
        self.setMinimumSize(480, 360)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self._closing = False

        self.controller = ViewerController()
        self.state = self.controller.state
        self.session_store = SessionStore()
        self.source_loader = SourceLoader(self.controller, self.session_store, parent=self)
        self.position_saver = PositionSaver(self.session_store, parent=self)
        self.opener = SourceOpener(
            self,
            self.controller,
            self.source_loader,
            self.session_store,
        )

        self.image_view = ImageView()
        # QGraphicsView accepts drops by default, which would consume file drops
        # before MainWindow can validate and load them.
        self.image_view.setAcceptDrops(False)
        self.presenter = ImagePresenter(self.controller, self.image_view, self)
        self.controls_panel = ViewerControls()
        self.info_panel = ViewerInfoPanel()
        self.issue_dialog = IssueDialog(self)
        self.shortcut_help_dialog = ShortcutHelpDialog(self)
        self.status = ViewerStatus(
            self.controller,
            self.presenter,
            self.source_loader,
            self.controls_panel,
            self.info_panel,
            self.issue_dialog,
            self.image_view,
        )

        self.viewer_surface = ViewerSurface(
            self.image_view,
            self.controls_panel,
            self.info_panel,
        )
        self.setCentralWidget(self.viewer_surface)
        self.overlays = OverlayController(self.viewer_surface, self.isFullScreen, parent=self)
        self._close_poll_timer = QTimer(self)
        self._close_poll_timer.setInterval(50)
        self._close_poll_timer.timeout.connect(self._finish_close_when_idle)

        self._connect_controls()
        self._connect_sources()
        self._shortcuts = install_viewer_shortcuts(self)
        self.status.update_navigation()
        self.overlays.set_visible(False)
        QApplication.instance().installEventFilter(self)
        self.opener.schedule_restore()
        QTimer.singleShot(0, self.image_view.setFocus)

    @property
    def current_context(self) -> FolderContext | None:
        return self.controller.current_context

    # Commands used by buttons, shortcuts and the macOS open event.

    def open_folder(self) -> None:
        self.opener.choose_folder()

    def open_archive(self) -> None:
        self.opener.choose_archive()

    def open_path(self, path: Path) -> None:
        self.opener.open_path(path)

    def refresh_source(self) -> None:
        self.opener.refresh()

    def open_next_sibling_folder(self) -> None:
        self.opener.open_sibling(1)

    def open_previous_sibling_folder(self) -> None:
        self.opener.open_sibling(-1)

    def cancel_scan(self) -> None:
        if self.source_loader.cancel_current():
            self.controls_panel.cancel_scan_button.setEnabled(False)
            self.overlays.show_temporarily()

    def show_next_image(self) -> None:
        if self.state.move_next():
            self.presenter.show_current()

    def show_previous_image(self) -> None:
        if self.state.move_previous():
            self.presenter.show_current()

    def show_next_archive(self) -> None:
        if self.state.move_next_archive():
            self.presenter.show_current()

    def show_previous_archive(self) -> None:
        if self.state.move_previous_archive():
            self.presenter.show_current()

    def show_issues(self) -> None:
        messages = self.status.issue_messages()
        if not messages:
            return
        self.issue_dialog.set_messages(messages)
        self._show_dialog(self.issue_dialog)

    def show_shortcut_help(self) -> None:
        self._show_dialog(self.shortcut_help_dialog)

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
            return
        self.showFullScreen()
        self._sync_window_state()

    def exit_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        self._sync_window_state()

    # Qt event handlers.

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if dropped_source(event.mimeData()) is None:
            event.ignore()
            return
        event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        source = dropped_source(event.mimeData())
        if source is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self.opener.open_path(source)

    def closeEvent(self, event) -> None:  # noqa: N802
        # Stop every input path first; workers may still need a moment.
        self._closing = True
        self.setAcceptDrops(False)
        self._shortcuts.set_enabled(False)
        self.controls_panel.setEnabled(False)
        self.image_view.setEnabled(False)
        self.overlays.stop()
        self.opener.begin_shutdown()
        self.source_loader.begin_shutdown()
        self.presenter.begin_shutdown()
        if self.source_loader.scanner.active_count or not self.presenter.wait_for_done(0):
            event.ignore()
            self.status.set_status("작업 종료 중…")
            self.overlays.set_visible(True)
            self._close_poll_timer.start()
            return

        self._close_poll_timer.stop()
        self.position_saver.flush()
        set_menu_bar_auto_hidden(False)
        QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if self._closing:
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.FileOpen:
            # macOS delivers Finder "Open With" and Dock drops this way.
            self.opener.open_path(Path(event.file()))
            self.raise_()
            self.activateWindow()
            return True
        if event.type() == QEvent.Type.MouseMove:
            self.overlays.show_temporarily()
        return super().eventFilter(watched, event)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0, self._sync_window_state)

    # Wiring and signal handlers.

    def _connect_controls(self) -> None:
        controls = self.controls_panel
        controls.layout_changed.connect(self.viewer_surface.position_floating_panels)
        for button, command in (
            (controls.open_button, self.open_folder),
            (controls.open_archive_button, self.open_archive),
            (controls.previous_folder_button, self.open_previous_sibling_folder),
            (controls.next_folder_button, self.open_next_sibling_folder),
            (controls.refresh_button, self.refresh_source),
            (controls.cancel_scan_button, self.cancel_scan),
            (controls.previous_archive_button, self.show_previous_archive),
            (controls.next_archive_button, self.show_next_archive),
            (controls.previous_button, self.show_previous_image),
            (controls.next_button, self.show_next_image),
            (controls.fit_button, self.image_view.request_fit),
            (controls.actual_size_button, self.image_view.actual_size),
            (controls.zoom_out_button, self.image_view.zoom_out),
            (controls.zoom_in_button, self.image_view.zoom_in),
            (controls.fullscreen_button, self.toggle_fullscreen),
            (controls.help_button, self.show_shortcut_help),
            (controls.minimize_button, self.showMinimized),
            (controls.close_button, self.close),
            (controls.issues_button, self.show_issues),
        ):
            button.clicked.connect(command)
        controls.encoding_combo.currentIndexChanged.connect(self._encoding_changed)
        self.issue_dialog.retry_requested.connect(self.refresh_source)

    def _connect_sources(self) -> None:
        self.opener.about_to_load.connect(self.status.select_encoding)
        self.opener.load_started.connect(self.overlays.show_temporarily)
        self.opener.message.connect(self._show_transient_status)
        self.presenter.entry_started.connect(self._entry_started)
        self.presenter.status_changed.connect(self.status.set_status)
        self.presenter.errors_changed.connect(self._errors_changed)
        self.source_loader.status_changed.connect(self.status.set_status)
        self.source_loader.scanning_changed.connect(self.controls_panel.set_scanning)
        self.source_loader.before_apply.connect(self.position_saver.flush)
        self.source_loader.source_applied.connect(self._source_applied)
        self.source_loader.source_completed.connect(self._source_completed)
        self.source_loader.source_rejected.connect(self._source_rejected)

    def _source_applied(self, context: FolderContext, result: ScanResult) -> None:
        self.presenter.reset_source()
        self.status.update_issues()
        if result.entries:
            self.presenter.show_current()
        else:
            self.status.show_empty_source(context, result)

    def _source_completed(self, _context: FolderContext, _result: ScanResult) -> None:
        # The previewed image stays on screen; only the surrounding state grows.
        self.status.update_issues()
        self.status.update_navigation()
        self.status.set_status(self.state.position_label)

    def _source_rejected(self, message: str) -> None:
        self._show_transient_status(message)
        self.status.update_navigation()

    def _entry_started(self, entry: ImageEntry) -> None:
        self.status.show_entry(entry)
        context = self.current_context
        if context is not None:
            self.position_saver.schedule(context, self.state)

    def _errors_changed(self) -> None:
        self.status.update_navigation()
        self.status.update_issues()
        if self.presenter.errors:
            self.overlays.show_temporarily()

    def _encoding_changed(self) -> None:
        self.opener.change_encoding(self.controls_panel.encoding_combo.currentData())

    def _show_transient_status(self, message: str) -> None:
        self.status.set_status(message)
        self.overlays.show_temporarily()

    def _show_dialog(self, dialog) -> None:
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _sync_window_state(self) -> None:
        fullscreen = self.isFullScreen()
        set_menu_bar_auto_hidden(fullscreen)
        self.controls_panel.fullscreen_button.setText("창모드" if fullscreen else "전체화면")
        self.overlays.sync_grip()

    def _finish_close_when_idle(self) -> None:
        if self.source_loader.scanner.active_count or not self.presenter.wait_for_done(0):
            return
        self._close_poll_timer.stop()
        self.close()
