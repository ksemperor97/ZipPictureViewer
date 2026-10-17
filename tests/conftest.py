from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from app_driver import ViewerApp


LaunchApp = Callable[..., ViewerApp]


@pytest.fixture(scope="session", autouse=True)
def built_app() -> None:
    """Build the debug app once per run unless a packaged app is under test."""

    if os.environ.get("ZPV_E2E_APP"):
        return
    env = dict(os.environ)
    if "DEVELOPER_DIR" not in env and Path("/Applications/Xcode.app").exists():
        env["DEVELOPER_DIR"] = "/Applications/Xcode.app/Contents/Developer"
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["swift", "build"], cwd=root, env=env, check=True)


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """An isolated settings directory shared by every launch in one test."""

    path = tmp_path / "config"
    path.mkdir()
    return path


@pytest.fixture
def launch_app(tmp_path: Path, config_dir: Path) -> Iterator[LaunchApp]:
    apps: list[ViewerApp] = []

    def launch(
        *args: str | Path,
        env: dict[str, str] | None = None,
        finder_files: list[Path] | None = None,
        language: str | None = "ko",
    ) -> ViewerApp:
        app = ViewerApp(
            tmp_path,
            config_dir,
            [str(arg) for arg in args],
            env,
            finder_files,
            language,
        )
        apps.append(app)
        return app.start()

    yield launch
    for app in apps:
        app.kill()
