"""Malformed ZIP64 values must become errors, never take the app down."""

from __future__ import annotations

from media import GREEN, hex_color, write_png, write_zip64_locator_only, write_zip64_member

HUGE = 2**64 - 16


def _collection_with(tmp_path, build) -> object:
    collection = tmp_path / "collection"
    build(collection)
    write_png(collection / "zz" / "ok.png", GREEN)
    return collection


def _assert_survives(app) -> None:
    """The good image is still reachable and the app keeps running."""

    state = app.state()
    if state["member"] != "ok.png":
        app.key("Right")
    app.wait_for_image("zz", "ok.png")
    assert app.pixel() == hex_color(GREEN)
    assert app.process.poll() is None, app.log_tail()
    assert app.close() == 0


def test_zip64_record_offset_overflow_is_reported(launch_app, tmp_path) -> None:
    collection = _collection_with(tmp_path, lambda c: write_zip64_locator_only(c / "bad.zip", HUGE))
    app = launch_app()
    app.drop(collection)
    app.wait_for(lambda s: s["issues_button"] == "오류 1", "the bad archive reported")
    _assert_survives(app)


def test_zip64_member_with_huge_compressed_size_is_reported(launch_app, tmp_path) -> None:
    collection = _collection_with(
        tmp_path,
        lambda c: write_zip64_member(c / "a.zip", "p1.png", uncompressed=100, compressed=2**63 + 5),
    )
    app = launch_app()
    app.drop(collection)
    app.wait_for(lambda s: s["member"] == "p1.png" and "이미지를 열 수 없습니다" in s["message"], "member error")
    _assert_survives(app)


def test_zip64_member_offset_overflow_is_reported(launch_app, tmp_path) -> None:
    collection = _collection_with(
        tmp_path,
        lambda c: write_zip64_member(c / "a.zip", "p1.png", uncompressed=100, compressed=10, offset=HUGE),
    )
    app = launch_app()
    app.drop(collection)
    app.wait_for(lambda s: s["member"] == "p1.png" and "이미지를 열 수 없습니다" in s["message"], "member error")
    _assert_survives(app)


def test_zip64_compression_ratio_overflow_is_reported(launch_app, tmp_path) -> None:
    collection = _collection_with(
        tmp_path,
        lambda c: write_zip64_member(c / "a.zip", "p1.png", uncompressed=100 * 2**20, compressed=2**60),
    )
    app = launch_app()
    app.drop(collection)
    app.wait_for(lambda s: s["member"] == "p1.png" and "이미지를 열 수 없습니다" in s["message"], "member error")
    _assert_survives(app)
