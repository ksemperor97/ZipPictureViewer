from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .viewer_widgets import FloatingPanel


class ElidingLabel(QLabel):
    """Middle-elide long paths while retaining a full copy action."""

    def __init__(self) -> None:
        super().__init__("")
        self._full_text = ""
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_copy_menu)

    @property
    def full_text(self) -> str:
        return self._full_text

    def setText(self, text: str) -> None:  # noqa: N802
        self._full_text = text
        self.setToolTip(text)
        self._refresh_elision()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_elision()

    def _refresh_elision(self) -> None:
        display_text = self.fontMetrics().elidedText(
            self._full_text,
            Qt.TextElideMode.ElideMiddle,
            max(40, self.width() - 8),
        )
        super().setText(display_text)

    def _show_copy_menu(self, position) -> None:
        menu = QMenu(self)
        copy_action = menu.addAction("전체 경로 복사")
        if menu.exec(self.mapToGlobal(position)) == copy_action:
            QApplication.clipboard().setText(self._full_text)


class ViewerControls(FloatingPanel):
    """Responsive command surface kept separate from viewer orchestration."""

    layout_changed = Signal()

    compact_button_names = (
        "open_button",
        "previous_button",
        "next_button",
        "close_button",
        "expand_button",
    )
    secondary_button_names = (
        "open_archive_button",
        "previous_folder_button",
        "next_folder_button",
        "refresh_button",
        "previous_archive_button",
        "next_archive_button",
        "issues_button",
        "fit_button",
        "actual_size_button",
        "zoom_out_button",
        "zoom_in_button",
        "fullscreen_button",
        "help_button",
        "cancel_scan_button",
        "minimize_button",
    )
    button_names = compact_button_names + secondary_button_names

    def __init__(self) -> None:
        super().__init__()
        self.open_button = QPushButton("폴더 열기")
        self.open_archive_button = QPushButton("ZIP 열기")
        self.previous_folder_button = QPushButton("이전 폴더")
        self.next_folder_button = QPushButton("다음 폴더")
        self.refresh_button = QPushButton("새로고침")
        self.previous_archive_button = QPushButton("↑ 이전 묶음")
        self.previous_button = QPushButton("← 이전")
        self.next_button = QPushButton("다음 →")
        self.next_archive_button = QPushButton("↓ 다음 묶음")
        self.issues_button = QPushButton("오류 0")
        self.fit_button = QPushButton("화면 맞춤")
        self.actual_size_button = QPushButton("100%")
        self.zoom_out_button = QPushButton("축소 −")
        self.zoom_in_button = QPushButton("확대 +")
        self.fullscreen_button = QPushButton("전체화면")
        self.help_button = QPushButton("도움말")
        self.cancel_scan_button = QPushButton("스캔 취소")
        self.minimize_button = QPushButton("최소화")
        self.close_button = QPushButton("닫기")
        self.expand_button = QPushButton("펼치기")
        self.status_label = QLabel("폴더 또는 ZIP 열기")
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItem("ZIP 이름: 자동", "auto")
        self.encoding_combo.addItem("ZIP 이름: CP949", "cp949")
        self.encoding_combo.addItem("ZIP 이름: CP437", "cp437")
        self.encoding_combo.setToolTip("현재 루트의 ZIP 파일명 인코딩")
        self.encoding_combo.setMinimumWidth(126)
        self._expanded = True
        self._build_layout()
        self.expand_button.clicked.connect(self.toggle_expanded)
        self.set_expanded(False)
        self.set_scanning(False)
        self.set_issue_count(0)

    def buttons(self) -> Iterable[QPushButton]:
        return (getattr(self, name) for name in self.button_names)

    def set_scanning(self, active: bool) -> None:
        self.cancel_scan_button.setEnabled(active)
        self.open_button.setEnabled(not active)
        self.open_archive_button.setEnabled(not active)
        self.encoding_combo.setEnabled(not active)

    def set_issue_count(self, count: int) -> None:
        self.issues_button.setText(f"오류 {count}")
        self.issues_button.setEnabled(count > 0)

    @property
    def expanded(self) -> bool:
        return self._expanded

    def toggle_expanded(self) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self.secondary_panel.setVisible(expanded)
        self.expand_button.setText("접기" if expanded else "펼치기")
        self.updateGeometry()
        self.adjustSize()
        self.layout_changed.emit()

    def _build_layout(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        compact_layout = QHBoxLayout()
        compact_layout.setContentsMargins(0, 0, 0, 0)
        compact_layout.setSpacing(6)
        for name in self.compact_button_names:
            compact_layout.addWidget(getattr(self, name))
        layout.addLayout(compact_layout)

        self.secondary_panel = QWidget()
        secondary_layout = QGridLayout(self.secondary_panel)
        secondary_layout.setContentsMargins(0, 0, 0, 0)
        secondary_layout.setHorizontalSpacing(6)
        secondary_layout.setVerticalSpacing(6)
        secondary_rows = (
            (
                self.open_archive_button,
                self.previous_folder_button,
                self.next_folder_button,
                self.refresh_button,
                self.cancel_scan_button,
            ),
            (
                self.previous_archive_button,
                self.next_archive_button,
                self.issues_button,
                self.fit_button,
                self.actual_size_button,
            ),
            (
                self.zoom_out_button,
                self.zoom_in_button,
                self.fullscreen_button,
                self.help_button,
                self.minimize_button,
            ),
        )
        for row, widgets in enumerate(secondary_rows):
            for column, widget in enumerate(widgets):
                secondary_layout.addWidget(widget, row, column)

        secondary_layout.addWidget(self.encoding_combo, 3, 0, 1, 2)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(
            "background-color: rgba(24, 24, 27, 235); "
            "border-radius: 4px; padding: 4px 8px;"
        )
        secondary_layout.addWidget(self.status_label, 3, 2, 1, 3)
        layout.addWidget(self.secondary_panel)
        self.setLayout(layout)


class ViewerInfoPanel(FloatingPanel):
    def __init__(self) -> None:
        super().__init__()
        self.file_label = ElidingLabel()
        self.file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_label.setMinimumWidth(320)
        self.file_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 7, 10, 7)
        layout.addWidget(self.file_label)
        self.setLayout(layout)
