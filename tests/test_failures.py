"""Broken, encrypted and unusual files never block the rest of a collection."""

from __future__ import annotations

import os
import time

from media import (
    BLUE,
    GREEN,
    RED,
    hex_color,
    png_bytes,
    write_aes_marked_zip,
    write_png,
    write_raw_zip,
    write_zipcrypto_zip,
)


def test_corrupt_image_and_bad_zip_are_isolated(launch_app, tmp_path) -> None:
    collection = tmp_path / "collection"
    collection.mkdir()
    (collection / "1-broken.png").write_bytes(b"not a png")
    write_png(collection / "2-good.png", GREEN)
    (collection / "bad.zip").write_bytes(b"not a zip")
    app = launch_app()

    app.drop(collection)
    state = app.wait_for(
        lambda s: s["member"] == "1-broken.png" and "이미지를 열 수 없습니다" in s["message"],
        "broken image placeholder",
    )
    assert state["entry_count"] == 2
    app.wait_for(lambda s: s["issues_button"] == "오류 2", "two reported issues")

    app.key("Right")
    app.wait_for_image("collection", "2-good.png")
    assert app.pixel() == hex_color(GREEN)


def test_empty_unsupported_and_unreadable_folders_explain_themselves(
    launch_app,
    tmp_path,
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    unsupported = tmp_path / "unsupported"
    unsupported.mkdir()
    (unsupported / "notes.txt").write_text("text")
    unreadable = tmp_path / "unreadable"
    unreadable.mkdir()
    (unreadable / "bad.zip").write_bytes(b"not a zip")
    app = launch_app()

    for folder, message in (
        (empty, "빈 폴더입니다"),
        (unsupported, "지원되는 이미지 형식이 없습니다"),
        (unreadable, "이미지 컨테이너를 읽지 못했습니다"),
    ):
        app.drop(folder)
        app.wait_for(
            lambda s, f=folder, m=message: s["source"] == str(f) and s["message"] == m,
            f"message for {folder.name}",
        )


def test_zipcrypto_archive_asks_for_a_password(launch_app, tmp_path) -> None:
    collection = tmp_path / "secret"
    write_zipcrypto_zip(collection / "locked.zip", "page.png", png_bytes(BLUE), "hunter2")
    app = launch_app()

    app.drop(collection)
    app.wait_for(lambda s: s["modal_title"] == "ZIP 암호", "password prompt")
    app.call("answer_dialog", text="hunter2")
    app.wait_for_image("locked.zip", "page.png")
    assert app.pixel() == hex_color(BLUE)


def test_cancelled_password_shows_an_error(launch_app, tmp_path) -> None:
    collection = tmp_path / "secret"
    write_zipcrypto_zip(collection / "locked.zip", "page.png", png_bytes(BLUE), "hunter2")
    app = launch_app()

    app.drop(collection)
    app.wait_for(lambda s: s["modal_title"] == "ZIP 암호", "password prompt")
    app.call("answer_dialog", accept=False)
    app.wait_for(lambda s: "ZIP 암호 입력을 취소했습니다" in s["message"], "cancel error")


def test_aes_archive_is_reported_as_unsupported(launch_app, tmp_path) -> None:
    collection = tmp_path / "aes"
    write_aes_marked_zip(collection / "aes.zip", "page.png")
    write_png(collection / "zz" / "next.png", RED)
    app = launch_app()

    app.drop(collection)
    app.wait_for(lambda s: "AES 방식" in s["message"], "AES error")
    app.key("Right")
    app.wait_for_image("zz", "next.png")


def test_legacy_korean_file_names_are_decoded(launch_app, tmp_path) -> None:
    collection = tmp_path / "korean"
    page = png_bytes(GREEN)
    write_raw_zip(
        collection / "book.zip",
        [("가1.png".encode("cp949"), page, 0, 0), ("가2.png".encode("cp949"), page, 0, 0)],
    )
    app = launch_app()

    app.drop(collection / "book.zip")
    state = app.wait_for_image("book.zip", "가1.png")
    assert state["file_label"].endswith("book.zip  |  가1.png")


def test_refresh_shows_a_replaced_image(launch_app, tmp_path) -> None:
    collection = tmp_path / "collection"
    image = write_png(collection / "page.png", RED)
    app = launch_app()
    app.drop(collection)
    app.wait_for_image("collection", "page.png")
    assert app.pixel() == hex_color(RED)

    write_png(image, BLUE)
    later = time.time() + 5
    os.utime(image, (later, later))
    app.key("R")
    app.wait_for(lambda s: s["has_image"] and app.pixel() == hex_color(BLUE), "new pixels")


def test_refresh_of_a_deleted_folder_keeps_the_current_view(launch_app, tmp_path) -> None:
    collection = tmp_path / "collection"
    image = write_png(collection / "page.png", RED)
    app = launch_app()
    app.drop(collection)
    app.wait_for_image("collection", "page.png")

    image.unlink()
    collection.rmdir()
    app.key("R")
    state = app.wait_for(lambda s: "열 수 없" in s["status"], "rejection status")
    assert state["source"] == str(collection)
    assert state["has_image"]
