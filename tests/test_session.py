"""Reading positions survive app restarts and re-opened archives."""

from __future__ import annotations

import sys

import pytest

from media import BLUE, GREEN, RED, write_book


def test_relaunch_restores_the_last_folder_and_page(launch_app, tmp_path) -> None:
    library = tmp_path / "library"
    write_book(library / "vol1.zip", [RED, GREEN])
    write_book(library / "vol2.zip", [BLUE, RED])
    app = launch_app()
    app.drop(library)
    app.wait_for_image("vol1.zip", "p1.png")
    app.key("Down")
    app.key("Right")
    app.wait_for_image("vol2.zip", "p2.png")
    assert app.close() == 0

    relaunched = launch_app()
    state = relaunched.wait_for_image("vol2.zip", "p2.png")
    assert state["source"] == str(library)
    assert state["status"] == "4 / 4"


def test_reopening_an_archive_resumes_inside_it(launch_app, tmp_path) -> None:
    library = tmp_path / "library"
    write_book(library / "vol1.zip", [RED, GREEN])
    write_book(library / "vol2.zip", [BLUE, RED, GREEN])
    app = launch_app()
    app.drop(library / "vol2.zip")
    app.wait_for_image("vol2.zip", "p1.png")
    app.key("Right")
    app.key("Right")
    app.wait_for_image("vol2.zip", "p3.png")

    app.drop(library / "vol1.zip")
    app.wait_for_image("vol1.zip", "p1.png")
    app.key("Right")
    app.wait_for_image("vol1.zip", "p2.png")
    assert app.close() == 0

    relaunched = launch_app()
    relaunched.wait_for_image("vol1.zip", "p2.png")
    relaunched.drop(library / "vol2.zip")
    relaunched.wait_for_image("vol2.zip", "p1.png")


def test_archive_in_home_folder_opens_alone(launch_app, tmp_path) -> None:
    home = tmp_path / "home"
    write_book(home / "book.zip", [RED])
    write_book(home / "other.zip", [BLUE])
    home_env = "USERPROFILE" if sys.platform == "win32" else "HOME"
    app = launch_app(env={home_env: str(home)})

    app.drop(home / "book.zip")
    state = app.wait_for_image("book.zip", "p1.png")
    assert state["source_kind"] == "archive"
    assert state["entry_count"] == 1


def test_corrupt_session_file_starts_cleanly(launch_app, config_dir, tmp_path) -> None:
    (config_dir / "session.json").write_text("{ not json")
    library = tmp_path / "library"
    write_book(library / "vol1.zip", [RED])
    app = launch_app()
    assert app.state()["source"] is None

    app.drop(library)
    app.wait_for_image("vol1.zip", "p1.png")
    assert app.close() == 0
    launch_app().wait_for_image("vol1.zip", "p1.png")


def test_missing_saved_folder_starts_empty(launch_app, tmp_path) -> None:
    library = tmp_path / "library"
    write_book(library / "vol1.zip", [RED])
    app = launch_app()
    app.drop(library)
    app.wait_for_image("vol1.zip", "p1.png")
    assert app.close() == 0
    (library / "vol1.zip").unlink()
    library.rmdir()

    state = launch_app().state()
    assert state["source"] is None
    assert state["message"] == "폴더 열기 또는 드래그"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX directory permissions")
def test_read_only_settings_folder_does_not_stop_viewing(
    launch_app,
    config_dir,
    tmp_path,
) -> None:
    library = tmp_path / "library"
    write_book(library / "vol1.zip", [RED, GREEN])
    config_dir.chmod(0o500)
    try:
        app = launch_app()
        app.drop(library)
        app.wait_for_image("vol1.zip", "p1.png")
        app.key("Right")
        app.wait_for_image("vol1.zip", "p2.png")
        assert app.close() == 0
    finally:
        config_dir.chmod(0o700)
    assert "Cannot save session" in app.log_tail(200)
