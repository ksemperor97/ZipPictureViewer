"""The UI speaks Korean or English and switches without a restart."""

from __future__ import annotations

from media import RED, write_png

APP_MENU = "ZipPictureViewer"
LANGUAGE_MENU = "언어 (Language)"


def test_english_interface(launch_app, tmp_path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    app = launch_app(language="en")
    assert app.state()["message"] == "Open a folder or drop one here"

    app.drop(empty)
    state = app.wait_for(lambda s: s["source"] == str(empty), "empty folder")
    assert state["message"] == "The folder is empty"
    app.key("Question")
    app.wait_for(lambda s: "Keyboard Shortcuts" in s["dialogs"], "English help window")


def test_language_switches_immediately_from_the_menu(launch_app, tmp_path) -> None:
    collection = tmp_path / "collection"
    collection.mkdir()
    (collection / "1-broken.png").write_bytes(b"not a png")
    write_png(collection / "2-good.png", RED)
    app = launch_app(language="ko")
    app.drop(collection)
    app.wait_for(lambda s: "이미지를 열 수 없습니다" in s["message"], "Korean error placeholder")
    app.key("Question")
    app.wait_for(lambda s: "단축키 도움말" in s["dialogs"], "Korean help window")

    app.call("choose_menu", path=[APP_MENU, LANGUAGE_MENU, "English"])
    state = app.wait_for(lambda s: "Cannot open the image" in s["message"], "error re-rendered in English")
    assert "Keyboard Shortcuts" in state["dialogs"]
    assert state["issues_button"].startswith("Issues")

    app.call("choose_menu", path=[APP_MENU, LANGUAGE_MENU, "한국어"])
    state = app.wait_for(lambda s: "이미지를 열 수 없습니다" in s["message"], "back to Korean")
    assert state["issues_button"].startswith("오류")


def test_system_default_follows_the_mac_language(launch_app, tmp_path) -> None:
    korean = launch_app("-AppleLanguages", "(ko)", language="system")
    assert korean.state()["message"] == "폴더 열기 또는 드래그"
    assert korean.close() == 0

    english = launch_app("-AppleLanguages", "(en)", language="system")
    assert english.state()["message"] == "Open a folder or drop one here"
