"""Animation, shutdown and the packaged runtime check."""

from __future__ import annotations

import os
import subprocess
import time

from app_driver import app_command
from media import BLUE, RED, animated_gif_bytes, hex_color, write_book


def test_animated_gif_plays(launch_app, tmp_path) -> None:
    collection = tmp_path / "anim"
    collection.mkdir()
    (collection / "loop.gif").write_bytes(animated_gif_bytes([RED, BLUE]))
    app = launch_app()

    app.drop(collection)
    app.wait_for(lambda s: s["member"] == "loop.gif" and s["movie_running"], "movie")
    seen = set()
    app.wait_for(
        lambda s: seen.add(app.pixel()) or {hex_color(RED), hex_color(BLUE)} <= seen,
        "both animation frames",
    )


def test_gif_that_breaks_mid_animation_shows_an_error(launch_app, tmp_path) -> None:
    collection = tmp_path / "anim"
    collection.mkdir()
    gif = animated_gif_bytes([RED, BLUE])
    (collection / "broken.gif").write_bytes(gif[: len(gif) - 12])
    app = launch_app()

    app.drop(collection)
    app.wait_for(
        lambda s: s["member"] == "broken.gif"
        and (s["has_image"] or "이미지를 열 수 없습니다" in s["message"]),
        "first frame or an error placeholder",
    )
    time.sleep(1.0)  # let playback reach the damaged frame
    assert app.process.poll() is None, app.log_tail()
    assert app.close() == 0


def test_closing_during_a_long_scan_exits_promptly(launch_app, tmp_path) -> None:
    library = tmp_path / "big"
    for index in range(1500):
        write_book(library / f"part{index:04}" / "book.zip", [RED])
    app = launch_app()

    app.drop(library)
    app.wait_for(lambda s: s["scanning"], "scan to start")
    assert app.close(timeout=10) == 0


def test_runtime_smoke_check_passes(tmp_path) -> None:
    env = dict(os.environ, ZIP_PICTURE_VIEWER_CONFIG_DIR=str(tmp_path))
    result = subprocess.run(
        [*app_command(), "--smoke-test"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
