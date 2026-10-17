from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from app_driver import ViewerApp


LaunchApp = Callable[..., ViewerApp]


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """An isolated settings directory shared by every launch in one test."""

    path = tmp_path / "config"
    path.mkdir()
    return path


@pytest.fixture
def launch_app(tmp_path: Path, config_dir: Path) -> Iterator[LaunchApp]:
    apps: list[ViewerApp] = []

    def launch(*args: str | Path, env: dict[str, str] | None = None) -> ViewerApp:
        app = ViewerApp(tmp_path, config_dir, [str(arg) for arg in args], env)
        apps.append(app)
        return app.start()

    yield launch
    for app in apps:
        app.kill()
