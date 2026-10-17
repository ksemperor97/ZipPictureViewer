"""Large folders show the relevant images before the whole scan finishes."""

from __future__ import annotations

from media import BLUE, RED, write_book

VOLUMES = 2000


def _big_library(root):
    library = root / "big"
    for index in range(VOLUMES):
        write_book(library / f"vol{index:04}.zip", [BLUE if index == 1500 else RED, RED])
    return library


def _shown_while_scanning(state, archive, member) -> bool:
    return (
        state["archive"] == archive
        and state["member"] == member
        and state["has_image"]
        and state["scanning"]
    )


def test_dropped_archive_appears_before_the_scan_finishes(launch_app, tmp_path) -> None:
    library = _big_library(tmp_path)
    app = launch_app()

    app.drop(library / "vol1500.zip")
    app.wait_for(
        lambda s: _shown_while_scanning(s, "vol1500.zip", "p1.png"),
        "chosen archive shown while scanning",
    )
    state = app.wait_for_idle()
    assert state["entry_count"] == VOLUMES * 2
    assert state["archive"] == "vol1500.zip" and state["member"] == "p1.png"
    assert state["status"] == f"{1500 * 2 + 1} / {VOLUMES * 2}"

    app.key("Down")
    app.wait_for_image("vol1501.zip", "p1.png")


def test_relaunch_shows_the_saved_page_while_scanning(launch_app, tmp_path) -> None:
    library = _big_library(tmp_path)
    app = launch_app()
    app.drop(library / "vol1500.zip")
    app.wait_for_idle()
    app.key("Right")
    app.wait_for_image("vol1500.zip", "p2.png")
    assert app.close() == 0

    relaunched = launch_app()
    relaunched.wait_for(
        lambda s: _shown_while_scanning(s, "vol1500.zip", "p2.png"),
        "saved page shown while scanning",
    )
    state = relaunched.wait_for_idle()
    assert state["member"] == "p2.png" and state["archive"] == "vol1500.zip"


def test_neighbouring_archives_open_while_still_scanning(launch_app, tmp_path) -> None:
    # A folder of many archives (like one on a slow external drive): ↑/↓ must
    # reach the neighbours long before the whole folder has been read.
    library = tmp_path / "huge"
    for index in range(3000):
        write_book(library / f"vol{index:04}.zip", [RED])
    app = launch_app()

    app.drop(library / "vol1500.zip")
    app.wait_for(lambda s: _shown_while_scanning(s, "vol1500.zip", "p1.png"), "chosen archive")
    app.key("Down")
    app.wait_for(lambda s: _shown_while_scanning(s, "vol1501.zip", "p1.png"), "next archive while scanning")
    app.key("Up")
    app.key("Up")
    app.wait_for(lambda s: _shown_while_scanning(s, "vol1499.zip", "p1.png"), "previous archive while scanning")
    app.key("Right")
    app.wait_for_image("vol1500.zip", "p1.png")

    state = app.wait_for_idle()
    assert state["entry_count"] == 3000
    assert state["archive"] == "vol1500.zip"
