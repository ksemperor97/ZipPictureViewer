from __future__ import annotations

from pathlib import Path

import pytest

from zippictureviewer.folder_context import FolderContext


def test_folder_context_keeps_symlink_alias_for_logical_path(tmp_path: Path) -> None:
    real_collection = tmp_path / "storage" / "collection"
    real_collection.mkdir(parents=True)
    alias = tmp_path / "selected-collection"
    _create_directory_symlink(alias, real_collection)

    context = FolderContext.from_path(alias)

    assert context.logical_path == alias.absolute()
    assert context.access_path == real_collection.resolve()
    assert context.source_kind == "folder"
    assert context.is_accessible


def test_folder_context_supports_a_single_archive(tmp_path: Path) -> None:
    archive = tmp_path / "book.cbz"
    archive.touch()

    context = FolderContext.from_path(archive)

    assert context.logical_path == archive.absolute()
    assert context.access_path == archive.resolve()
    assert context.source_kind == "archive"
    assert context.is_accessible


def test_folder_context_round_trips_serialized_paths(tmp_path: Path) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    context = FolderContext.from_path(root)

    restored = FolderContext.from_dict(context.to_dict())

    assert restored == context
    assert FolderContext.from_dict({"logical_path": str(root)}) is None


def _create_directory_symlink(alias: Path, target: Path) -> None:
    try:
        alias.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlinks are unavailable: {error}")
