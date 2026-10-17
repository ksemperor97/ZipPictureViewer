from __future__ import annotations

from pathlib import Path

from scripts.check_release_version import read_project_version
from zippictureviewer import __version__


def test_runtime_version_matches_project_metadata() -> None:
    project_root = Path(__file__).resolve().parents[1]
    assert __version__ == read_project_version(project_root)
