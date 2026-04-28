from __future__ import annotations

import sys


def set_menu_bar_auto_hidden(enabled: bool) -> None:
    if sys.platform != "darwin":
        return

    try:
        from AppKit import (  # type: ignore[import-not-found]
            NSApp,
            NSApplicationPresentationAutoHideDock,
            NSApplicationPresentationAutoHideMenuBar,
            NSApplicationPresentationDefault,
        )
    except Exception:
        return

    if enabled:
        options = (
            NSApplicationPresentationAutoHideDock
            | NSApplicationPresentationAutoHideMenuBar
        )
    else:
        options = NSApplicationPresentationDefault

    try:
        NSApp.setPresentationOptions_(options)
    except Exception:
        return
