"""Opening collections from the command line and from Finder."""

from __future__ import annotations

import pytest

from app_driver import packaged_macos_bundle
from media import BLUE, GREEN, RED, hex_color, write_book, write_png


def _library(root):
    library = root / "library"
    write_book(library / "vol1.zip", [RED])
    write_book(library / "vol2.zip", [BLUE, GREEN])
    return library


def test_command_line_folder_opens_at_launch(launch_app, tmp_path) -> None:
    library = _library(tmp_path)
    app = launch_app(library)

    state = app.wait_for_image("vol1.zip", "p1.png")
    assert state["source"] == str(library)
    assert app.pixel() == hex_color(RED)


def test_command_line_archive_opens_its_folder(launch_app, tmp_path) -> None:
    library = _library(tmp_path)
    app = launch_app(library / "vol2.zip")

    state = app.wait_for_image("vol2.zip", "p1.png")
    assert state["source"] == str(library)
    assert state["entry_count"] == 3


def test_command_line_path_wins_over_the_saved_session(launch_app, tmp_path) -> None:
    library = _library(tmp_path)
    other = tmp_path / "other"
    write_png(other / "single.png", GREEN)
    first = launch_app()
    first.drop(library)
    first.wait_for_image("vol1.zip", "p1.png")
    assert first.close() == 0

    app = launch_app(other)
    state = app.wait_for_image("other", "single.png")
    assert state["source"] == str(other)


def test_unopenable_command_line_path_is_reported(launch_app, tmp_path) -> None:
    app = launch_app(tmp_path / "missing.zip")

    state = app.wait_for(lambda s: "열 수 없는 경로" in s["status"], "rejection status")
    assert state["source"] is None


def test_finder_open_event_opens_the_archive_folder(launch_app, tmp_path) -> None:
    library = _library(tmp_path)
    app = launch_app()

    app.call("file_open", path=str(library / "vol2.zip"))
    state = app.wait_for_image("vol2.zip", "p1.png")
    assert state["source"] == str(library)

    app.call("file_open", path=str(library / "vol1.zip"))
    app.wait_for_image("vol1.zip", "p1.png")


@pytest.mark.skipif(
    packaged_macos_bundle() is None,
    reason="needs ZPV_E2E_APP pointing into a packaged macOS .app",
)
def test_launch_services_opens_an_archive_like_finder(launch_app, tmp_path) -> None:
    library = _library(tmp_path)
    app = launch_app(finder_files=[library / "vol2.zip"])

    state = app.wait_for_image("vol2.zip", "p1.png")
    assert state["source"] == str(library)
    assert app.close() == 0
