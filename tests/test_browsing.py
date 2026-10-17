"""Opening collections and moving through them, as a user does it."""

from __future__ import annotations

from pathlib import Path

from media import BLUE, GREEN, RED, YELLOW, hex_color, write_book, write_png


def _library(root: Path) -> Path:
    library = root / "library"
    write_book(library / "vol1.zip", [RED, GREEN])
    write_book(library / "vol2.zip", [BLUE])
    write_book(library / "vol10.cbz", [YELLOW])
    return library


def test_dropped_folder_shows_images_in_natural_order(launch_app, tmp_path) -> None:
    library = _library(tmp_path)
    write_png(library / "zz-loose" / "a.png", GREEN)
    app = launch_app()
    assert app.state()["message"] == "폴더 열기 또는 드래그"

    assert app.drop(library)
    state = app.wait_for_image("vol1.zip", "p1.png")
    assert state["status"] == "1 / 5"
    assert app.pixel() == hex_color(RED)

    app.key("Right")
    app.wait_for_image("vol1.zip", "p2.png")
    assert app.pixel() == hex_color(GREEN)
    app.key("Space")
    app.wait_for_image("vol2.zip", "p1.png")
    app.key("Down")
    app.wait_for_image("vol10.cbz", "p1.png")
    app.key("Down")
    app.wait_for_image("zz-loose", "a.png")
    app.key("Right")  # the last image wraps to the first
    app.wait_for_image("vol1.zip", "p1.png")
    app.key("Up")
    app.wait_for_image("zz-loose", "a.png")
    app.key("Left")
    app.wait_for_image("vol10.cbz", "p1.png")
    assert app.close() == 0


def test_dropping_one_archive_opens_its_whole_folder(launch_app, tmp_path) -> None:
    library = _library(tmp_path)
    app = launch_app()

    assert app.drop(library / "vol2.zip")
    state = app.wait_for_image("vol2.zip", "p1.png")
    assert state["source"] == str(library)
    assert state["source_kind"] == "folder"
    assert state["entry_count"] == 4
    assert app.pixel() == hex_color(BLUE)

    app.key("Down")
    app.wait_for_image("vol10.cbz", "p1.png")
    app.key("Down")
    app.wait_for_image("vol1.zip", "p1.png")


def test_drop_lands_anywhere_on_the_window(launch_app, tmp_path) -> None:
    library = _library(tmp_path)
    app = launch_app()

    for x, y in ((0.5, 0.5), (0.05, 0.95), (0.95, 0.05)):
        assert app.drop(library, x=x, y=y)
        app.wait_for_image("vol1.zip", "p1.png")


def test_unsupported_drops_are_refused(launch_app, tmp_path) -> None:
    text_file = tmp_path / "notes.txt"
    text_file.write_text("not a collection")
    app = launch_app()

    assert not app.drop(text_file)
    assert not app.drop(tmp_path / "missing.zip")
    assert app.state()["source"] is None


def test_buttons_respond_to_real_mouse_clicks(launch_app, tmp_path) -> None:
    app = launch_app()
    app.drop(_library(tmp_path))
    app.wait_for_image("vol1.zip", "p1.png")

    app.click("next_button")
    app.wait_for_image("vol1.zip", "p2.png")
    app.click("previous_button")
    app.wait_for_image("vol1.zip", "p1.png")
    app.click("expand_button")
    app.wait_for(lambda s: s["controls_visible"], "expanded controls")
    app.click("next_archive_button")
    app.wait_for_image("vol2.zip", "p1.png")


def test_sibling_folder_shortcut_opens_the_next_folder(launch_app, tmp_path) -> None:
    first = tmp_path / "series" / "part1"
    second = tmp_path / "series" / "part2"
    write_png(first / "a.png", RED)
    write_png(second / "b.png", BLUE)
    app = launch_app()
    app.drop(first)
    app.wait_for_image("part1", "a.png")

    app.key("Down", "ctrl")
    state = app.wait_for_image("part2", "b.png")
    assert state["source"] == str(second)
    app.key("Up", "ctrl")
    app.wait_for_image("part1", "a.png")


def test_zoom_shortcuts_and_double_click(launch_app, tmp_path) -> None:
    app = launch_app()
    app.drop(_library(tmp_path))
    fitted = app.wait_for_image("vol1.zip", "p1.png")
    assert fitted["fit_mode"] and fitted["zoom"] > 1

    app.key("1")
    app.wait_for(lambda s: not s["fit_mode"] and s["zoom"] == 1, "100% view")
    app.key("0")
    app.wait_for(lambda s: s["fit_mode"] and s["zoom"] == fitted["zoom"], "fit view")
    app.call("double_click")
    app.wait_for(lambda s: not s["fit_mode"], "double-click to 100%")
    app.key("Plus")
    app.wait_for(lambda s: s["zoom"] > 1, "zoom in")


def test_fullscreen_toggle_and_escape(launch_app, tmp_path) -> None:
    app = launch_app()
    app.key("F")
    app.wait_for(lambda s: s["fullscreen"], "fullscreen")
    app.key("Escape")
    app.wait_for(lambda s: not s["fullscreen"], "windowed")


def test_help_and_issue_windows_open(launch_app, tmp_path) -> None:
    (tmp_path / "collection").mkdir()
    (tmp_path / "collection" / "broken.zip").write_bytes(b"not a zip")
    write_png(tmp_path / "collection" / "ok.png", RED)
    app = launch_app()
    app.key("Question")
    app.wait_for(lambda s: "단축키" in " ".join(s["dialogs"]), "shortcut help")

    app.drop(tmp_path / "collection")
    app.wait_for_image("collection", "ok.png")
    app.click("expand_button")
    app.click("issues_button")
    app.wait_for(lambda s: "읽지 못한 항목" in s["dialogs"], "issue window")
