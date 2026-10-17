"""Large folders show the relevant images before the whole scan finishes.

Scanning is slowed per container (like a slow external drive) so "while
scanning" is a deterministic condition rather than a race with a fast disk.
"""

from __future__ import annotations

from media import BLUE, RED, write_book

VOLUMES = 200
CHOSEN = 150
SLOW_DRIVE = {"ZIP_PICTURE_VIEWER_SCAN_DELAY_MS": "20"}  # about 4 s per full scan


def _big_library(root):
    library = root / "big"
    for index in range(VOLUMES):
        write_book(library / f"vol{index:04}.zip", [BLUE if index == CHOSEN else RED, RED])
    return library


def _name(index: int) -> str:
    return f"vol{index:04}.zip"


def _shown_while_scanning(state, archive, member) -> bool:
    return (
        state["archive"] == archive
        and state["member"] == member
        and state["has_image"]
        and state["scanning"]
    )


def test_dropped_archive_appears_before_the_scan_finishes(launch_app, tmp_path) -> None:
    library = _big_library(tmp_path)
    app = launch_app(env=SLOW_DRIVE)

    app.drop(library / _name(CHOSEN))
    app.wait_for(
        lambda s: _shown_while_scanning(s, _name(CHOSEN), "p1.png"),
        "chosen archive shown while scanning",
    )
    state = app.wait_for_idle()
    assert state["entry_count"] == VOLUMES * 2
    assert state["archive"] == _name(CHOSEN) and state["member"] == "p1.png"
    assert state["status"] == f"{CHOSEN * 2 + 1} / {VOLUMES * 2}"

    app.key("Down")
    app.wait_for_image(_name(CHOSEN + 1), "p1.png")


def test_relaunch_shows_the_saved_page_while_scanning(launch_app, tmp_path) -> None:
    library = _big_library(tmp_path)
    app = launch_app()
    app.drop(library / _name(CHOSEN))
    app.wait_for_idle()
    app.key("Right")
    app.wait_for_image(_name(CHOSEN), "p2.png")
    assert app.close() == 0

    relaunched = launch_app(env=SLOW_DRIVE)
    relaunched.wait_for(
        lambda s: _shown_while_scanning(s, _name(CHOSEN), "p2.png"),
        "saved page shown while scanning",
    )
    state = relaunched.wait_for_idle()
    assert state["member"] == "p2.png" and state["archive"] == _name(CHOSEN)


def test_neighbouring_archives_open_while_still_scanning(launch_app, tmp_path) -> None:
    # ↑/↓ must reach the neighbours long before the whole folder is read.
    library = _big_library(tmp_path)
    app = launch_app(env=SLOW_DRIVE)

    app.drop(library / _name(CHOSEN))
    app.wait_for(lambda s: _shown_while_scanning(s, _name(CHOSEN), "p1.png"), "chosen archive")
    app.key("Down")
    app.wait_for(lambda s: _shown_while_scanning(s, _name(CHOSEN + 1), "p1.png"), "next archive while scanning")
    app.key("Up")
    app.key("Up")
    app.wait_for(lambda s: _shown_while_scanning(s, _name(CHOSEN - 1), "p1.png"), "previous archive while scanning")
    app.key("Right")
    app.wait_for(lambda s: _shown_while_scanning(s, _name(CHOSEN - 1), "p2.png"), "next page while scanning")

    state = app.wait_for_idle()
    assert state["entry_count"] == VOLUMES * 2
    assert state["archive"] == _name(CHOSEN - 1)
