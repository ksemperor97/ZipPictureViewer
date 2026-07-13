from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout, QWidget


SHORTCUT_HELP = """← / →, Space     이전 / 다음 이미지
↑ / ↓              이전 / 다음 묶음
Command + ↑ / ↓    이전 / 다음 형제 폴더 (macOS)
Ctrl + ↑ / ↓       이전 / 다음 형제 폴더 (Windows/Linux)
O                  폴더 열기
Ctrl + Shift + O   ZIP/CBZ 열기
R                  현재 원본 새로고침
0 / 1              화면 맞춤 / 100%
+ / -              확대 / 축소
F                  전체화면 전환
Esc                전체화면 종료
?                  단축키 도움말"""


class ShortcutHelpDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("단축키 도움말")
        self.setModal(False)
        self.resize(460, 360)

        details = QPlainTextEdit(SHORTCUT_HELP)
        details.setReadOnly(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.hide)

        layout = QVBoxLayout()
        layout.addWidget(details)
        layout.addWidget(buttons)
        self.setLayout(layout)
