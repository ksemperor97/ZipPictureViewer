from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizeGrip,
    QSizePolicy,
    QWidget,
)

from .archive_scanner import build_image_index
from .folder_navigation import child_folders, parent_folder, sibling_folder
from .image_cache import PixmapCache
from .mac_presentation import set_menu_bar_auto_hidden
from .session_store import SessionStore
from .viewer_state import ViewerState


class ImageLabel(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(QSize(320, 240))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: #171717; color: #f4f4f5;")


class FloatingPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self.setStyleSheet(
            """
            QFrame {
                background-color: rgba(24, 24, 27, 185);
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
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 42);
            }
            QPushButton:disabled {
                color: rgba(244, 244, 245, 90);
                background-color: rgba(255, 255, 255, 12);
            }
            """
        )


class ViewerSurface(QWidget):
    def __init__(
        self,
        image_label: ImageLabel,
        controls_panel: QWidget,
        info_panel: QWidget,
    ) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self.image_label = image_label
        self.controls_panel = controls_panel
        self.info_panel = info_panel
        self.resize_grip = QSizeGrip(self)
        self.resize_grip.setMouseTracking(True)

        self.image_label.setParent(self)
        self.controls_panel.setParent(self)
        self.info_panel.setParent(self)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.image_label.setGeometry(self.rect())
        self._position_floating_panels()

    def _position_floating_panels(self) -> None:
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
        info_width = min(info_size.width(), max_width)
        self.info_panel.setGeometry(
            max(margin, self.width() - info_width - margin),
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Zip Picture Viewer")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.resize(1100, 800)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.window_drag_offset: QPoint | None = None

        self.state = ViewerState()
        self.current_pixmap: QPixmap | None = None
        self.current_root: Path | None = None
        self.image_cache = PixmapCache()
        self.session_store = SessionStore()

        self.image_label = ImageLabel()
        self.status_label = QLabel("폴더 열기 또는 드래그")
        self.file_label = QLabel("")
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.previous_folder_button = QPushButton("이전 폴더")
        self.next_folder_button = QPushButton("다음 폴더")
        self.previous_archive_button = QPushButton("↑ 이전 묶음")
        self.next_archive_button = QPushButton("↓ 다음 묶음")
        self.previous_button = QPushButton("← 이전")
        self.next_button = QPushButton("다음 →")
        self.fit_button = QPushButton("화면 맞춤")
        self.fullscreen_button = QPushButton("전체화면")
        self.minimize_button = QPushButton("최소화")
        self.close_button = QPushButton("닫기")
        self.open_button = QPushButton("폴더 열기")
        self.controls_panel = FloatingPanel()
        self.info_panel = FloatingPanel()
        self.viewer_surface: ViewerSurface | None = None
        self.overlay_hide_timer = QTimer(self)
        self.overlay_hide_timer.setSingleShot(True)
        self.overlay_hide_timer.timeout.connect(self._hide_overlays)

        self._build_layout()
        self._connect_actions()
        self._update_navigation()
        self._set_overlays_visible(False)
        QApplication.instance().installEventFilter(self)
        QTimer.singleShot(0, self._restore_last_folder)

    def open_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "이미지가 들어있는 zip 폴더 선택")
        if not selected:
            return

        self.load_folder(Path(selected))

    def load_folder(self, root: Path) -> None:
        root = self._resolved_folder(root)
        self.current_root = root
        self.image_cache.clear()
        self.status_label.setText("스캔 중...")
        QApplication.processEvents()

        entries = build_image_index(root)
        restored_index = self.session_store.restore_index(root, entries)
        self.state.set_entries(entries, restored_index)

        if not entries:
            self.current_pixmap = None
            self.image_label.setText("이미지를 찾지 못했습니다")
            self.file_label.setText(str(root))
            self.status_label.setText("0 / 0")
            self._update_navigation()
            return

        self.show_current_image()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._dropped_folder(event.mimeData()) is None:
            event.ignore()
            return
        event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        dropped_folder = self._dropped_folder(event.mimeData())
        if dropped_folder is None:
            event.ignore()
            return

        event.acceptProposedAction()
        self.load_folder(dropped_folder)

    def show_current_image(self) -> None:
        entry = self.state.current_entry
        if entry is None:
            return

        try:
            self.current_pixmap = self.image_cache.get_or_load(entry)
        except Exception as exc:
            QMessageBox.warning(self, "이미지 로드 실패", f"{entry.member_name}\n\n{exc}")
            self.current_pixmap = None
            return

        self.file_label.setText(f"{entry.archive_path}  |  {entry.member_name}")
        self.status_label.setText(self.state.position_label)
        self._render_current_pixmap()
        self._update_navigation()
        self._save_position()
        QApplication.processEvents()
        self.image_cache.preload_around(self.state.entries, self.state.current_index)

    def show_next_image(self) -> None:
        if self.state.move_next():
            self.show_current_image()

    def show_previous_image(self) -> None:
        if self.state.move_previous():
            self.show_current_image()

    def show_next_archive(self) -> None:
        if self.state.move_next_archive():
            self.show_current_image()

    def show_previous_archive(self) -> None:
        if self.state.move_previous_archive():
            self.show_current_image()

    def open_next_sibling_folder(self) -> None:
        self._open_sibling_folder(1)

    def open_previous_sibling_folder(self) -> None:
        self._open_sibling_folder(-1)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._render_current_pixmap()

    def closeEvent(self, event) -> None:  # noqa: N802
        set_menu_bar_auto_hidden(False)
        super().closeEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.MouseMove:
            self._show_overlays_temporarily()

        if watched is self.image_label and self._handle_window_drag(event):
            return True
        return super().eventFilter(watched, event)

    def _build_layout(self) -> None:
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(8, 8, 8, 8)
        controls_layout.setSpacing(6)
        controls_layout.addWidget(self.open_button)
        controls_layout.addWidget(self.previous_folder_button)
        controls_layout.addWidget(self.next_folder_button)
        controls_layout.addWidget(self.previous_archive_button)
        controls_layout.addWidget(self.previous_button)
        controls_layout.addWidget(self.next_button)
        controls_layout.addWidget(self.next_archive_button)
        controls_layout.addWidget(self.fit_button)
        controls_layout.addWidget(self.fullscreen_button)
        controls_layout.addWidget(self.minimize_button)
        controls_layout.addWidget(self.close_button)
        controls_layout.addWidget(self.status_label)
        self.controls_panel.setLayout(controls_layout)

        self.file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_label.setMinimumWidth(360)

        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(10, 7, 10, 7)
        info_layout.addWidget(self.file_label)
        self.info_panel.setLayout(info_layout)

        self.viewer_surface = ViewerSurface(
            self.image_label,
            self.controls_panel,
            self.info_panel,
        )
        self.setCentralWidget(self.viewer_surface)

    def _connect_actions(self) -> None:
        self.open_button.clicked.connect(self.open_folder)
        self.previous_folder_button.clicked.connect(self.open_previous_sibling_folder)
        self.next_folder_button.clicked.connect(self.open_next_sibling_folder)
        self.previous_archive_button.clicked.connect(self.show_previous_archive)
        self.next_archive_button.clicked.connect(self.show_next_archive)
        self.previous_button.clicked.connect(self.show_previous_image)
        self.next_button.clicked.connect(self.show_next_image)
        self.fit_button.clicked.connect(self._render_current_pixmap)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.minimize_button.clicked.connect(self.showMinimized)
        self.close_button.clicked.connect(self.close)

        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self.show_previous_image)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=self.show_next_image)
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, activated=self.show_previous_archive)
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, activated=self.show_next_archive)
        QShortcut(QKeySequence("Meta+Up"), self, activated=self.open_previous_sibling_folder)
        QShortcut(QKeySequence("Meta+Down"), self, activated=self.open_next_sibling_folder)
        QShortcut(QKeySequence("Ctrl+Up"), self, activated=self.open_previous_sibling_folder)
        QShortcut(QKeySequence("Ctrl+Down"), self, activated=self.open_next_sibling_folder)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.show_next_image)
        QShortcut(QKeySequence("O"), self, activated=self.open_folder)
        QShortcut(QKeySequence("F"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.exit_fullscreen)
        self.image_label.installEventFilter(self)

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
            return

        set_menu_bar_auto_hidden(True)
        self.showFullScreen()
        self.fullscreen_button.setText("창모드")

    def exit_fullscreen(self) -> None:
        if self.isFullScreen():
            set_menu_bar_auto_hidden(False)
            self.showNormal()
            self.fullscreen_button.setText("전체화면")

    def _render_current_pixmap(self) -> None:
        if self.current_pixmap is None:
            return

        target_size = self.image_label.size()
        scaled = self.current_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)

    def _update_navigation(self) -> None:
        has_entries = self.state.has_entries
        has_folder = self.current_root is not None
        self.previous_folder_button.setEnabled(has_folder)
        self.next_folder_button.setEnabled(has_folder)
        self.previous_archive_button.setEnabled(has_entries and self.state.has_previous_archive())
        self.next_archive_button.setEnabled(has_entries and self.state.has_next_archive())
        self.previous_button.setEnabled(has_entries and self.state.current_index > 0)
        self.next_button.setEnabled(has_entries)
        self.fit_button.setEnabled(has_entries)

    def _dropped_folder(self, mime_data) -> Path | None:
        if not mime_data.hasUrls():
            return None

        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.is_dir():
                return path
        return None

    def _save_position(self) -> None:
        entry = self.state.current_entry
        if self.current_root is None or entry is None:
            return

        self.session_store.save_position(
            self.current_root,
            entry,
            self.state.current_index,
        )

    def _restore_last_folder(self) -> None:
        if self.current_root is not None:
            return

        last_root = self.session_store.last_root()
        if last_root is None:
            return

        self.load_folder(last_root)

    def _show_overlays_temporarily(self) -> None:
        self._set_overlays_visible(True)
        self.overlay_hide_timer.start(1600)

    def _hide_overlays(self) -> None:
        if self.controls_panel.underMouse() or self.info_panel.underMouse():
            self.overlay_hide_timer.start(800)
            return
        self._set_overlays_visible(False)

    def _set_overlays_visible(self, visible: bool) -> None:
        self.controls_panel.setVisible(visible)
        self.info_panel.setVisible(visible and bool(self.file_label.text()))
        if self.viewer_surface is not None:
            self.viewer_surface.resize_grip.setVisible(visible and not self.isFullScreen())

    def _open_sibling_folder(self, step: int) -> None:
        for anchor in self._sibling_navigation_anchors():
            folder = sibling_folder(anchor, step)
            if folder is not None:
                self.load_folder(folder)
                return
        self._show_folder_navigation_status("형제 폴더를 찾지 못했습니다")

    def _sibling_navigation_anchors(self) -> list[Path]:
        anchors: list[Path] = []
        entry = self.state.current_entry
        if entry is not None:
            if entry.archive_path.is_dir():
                anchors.append(entry.archive_path.parent)
                anchors.append(entry.archive_path)
            else:
                anchors.append(entry.archive_path.parent)

        if self.current_root is not None:
            anchors.append(self.current_root)

        unique_anchors: list[Path] = []
        for anchor in anchors:
            resolved = self._resolved_folder(anchor)
            if resolved not in unique_anchors:
                unique_anchors.append(resolved)
        return unique_anchors

    def _show_folder_navigation_status(self, message: str) -> None:
        self.status_label.setText(f"{message}  {self._folder_navigation_debug_label()}")
        self._show_overlays_temporarily()

    def _folder_navigation_debug_label(self) -> str:
        anchors = self._sibling_navigation_anchors()
        if not anchors:
            return ""

        anchor = anchors[0]
        parent = parent_folder(anchor)
        if parent is None:
            return f"기준: {anchor}"

        siblings = child_folders(parent)
        sibling_names = ", ".join(path.name for path in siblings[:8])
        if len(siblings) > 8:
            sibling_names += ", ..."
        return f"기준: {anchor.name} / 형제: {sibling_names or '없음'}"

    def _resolved_folder(self, folder: Path) -> Path:
        try:
            return folder.resolve()
        except OSError:
            return folder

    def _handle_window_drag(self, event) -> bool:
        if self.isFullScreen():
            self.window_drag_offset = None
            return False

        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            self.window_drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
            return True

        if event.type() == QEvent.Type.MouseMove:
            if self.window_drag_offset is None:
                return False
            if not event.buttons() & Qt.MouseButton.LeftButton:
                return False
            self.move(event.globalPosition().toPoint() - self.window_drag_offset)
            event.accept()
            return True

        if event.type() == QEvent.Type.MouseButtonRelease:
            self.window_drag_offset = None
            return False

        return False


def run_app() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()
