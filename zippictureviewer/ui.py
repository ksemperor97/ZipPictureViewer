from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from .viewer_window import MainWindow


def run_app(argv: Sequence[str] | None = None) -> int:
    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName("ZipPictureViewer")
    window = MainWindow()
    window.show()
    return app.exec()


__all__ = ["MainWindow", "run_app"]
