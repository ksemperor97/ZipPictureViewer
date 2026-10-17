from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .viewer_window import MainWindow


def run_app(
    argv: Sequence[str] | None = None,
    *,
    automation_handshake: str | None = None,
) -> int:
    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName("ZipPictureViewer")
    window = MainWindow()
    window.show()
    if automation_handshake:
        from .automation import AutomationServer

        AutomationServer(window, Path(automation_handshake))
    startup_path = _startup_path(app.arguments()[1:])
    if startup_path is not None:
        window.open_path(startup_path)
    return app.exec()


def _startup_path(arguments: Sequence[str]) -> Path | None:
    """Return the first path argument; QApplication already removed Qt options."""

    for argument in arguments:
        if not argument.startswith("-"):
            return Path(argument)
    return None


__all__ = ["MainWindow", "run_app"]
