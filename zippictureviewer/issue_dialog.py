from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class IssueDialog(QDialog):
    """Modeless, complete error report with a collection-level retry action."""

    retry_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("읽지 못한 항목")
        self.setModal(False)
        self.resize(760, 480)

        self.summary_label = QLabel("오류 0개")
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.copy_button = QPushButton("전체 복사")
        self.retry_button = QPushButton("현재 원본 다시 시도")
        self.close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.copy_button.clicked.connect(self._copy_all)
        self.retry_button.clicked.connect(self.retry_requested)
        self.close_buttons.rejected.connect(self.hide)

        action_layout = QHBoxLayout()
        action_layout.addWidget(self.copy_button)
        action_layout.addWidget(self.retry_button)
        action_layout.addStretch(1)
        action_layout.addWidget(self.close_buttons)

        layout = QVBoxLayout()
        layout.addWidget(self.summary_label)
        layout.addWidget(self.details, 1)
        layout.addLayout(action_layout)
        self.setLayout(layout)
        self.set_messages([])

    def set_messages(self, messages: Sequence[str]) -> None:
        count = len(messages)
        self.summary_label.setText(f"오류 {count}개 · 모든 항목 표시")
        self.details.setPlainText("\n\n".join(messages))
        self.copy_button.setEnabled(count > 0)
        self.retry_button.setEnabled(count > 0)

    def _copy_all(self) -> None:
        QApplication.clipboard().setText(self.details.toPlainText())
