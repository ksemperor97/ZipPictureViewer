from __future__ import annotations

import sys


def set_menu_bar_auto_hidden(enabled: bool) -> None:
    if sys.platform != "darwin":
        return

    # pyobjc is a declared macOS dependency and bundled by the spec.
    from AppKit import (  # type: ignore[import-not-found]
        NSApp,
        NSApplicationPresentationAutoHideDock,
        NSApplicationPresentationAutoHideMenuBar,
        NSApplicationPresentationDefault,
    )

    application = NSApp()  # pyobjc's NSApp proxy returns None without an app
    if application is None:
        return  # e.g. on the offscreen Qt platform

    if enabled:
        options = (
            NSApplicationPresentationAutoHideDock
            | NSApplicationPresentationAutoHideMenuBar
        )
    else:
        options = NSApplicationPresentationDefault

    application.setPresentationOptions_(options)
