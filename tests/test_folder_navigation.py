from __future__ import annotations

from pathlib import Path

import pytest

from zippictureviewer.folder_context import FolderContext
from zippictureviewer.folder_navigation import (
    child_folders,
    containing_folder_context,
    sibling_context,
    sibling_folder,
)


def test_sibling_folder_wraps_in_natural_order(tmp_path: Path) -> None:
    folder_10 = tmp_path / "folder10"
    folder_2 = tmp_path / "folder2"
    folder_1 = tmp_path / "folder1"
    for folder in (folder_10, folder_2, folder_1):
        folder.mkdir()

    assert child_folders(tmp_path) == [folder_1, folder_2, folder_10]
    assert sibling_folder(folder_2, 1) == folder_10
    assert sibling_folder(folder_10, 1) == folder_1
    assert sibling_folder(folder_1, -1) == folder_10


def test_sibling_navigation_preserves_symlink_parent_context(tmp_path: Path) -> None:
    real_parent = tmp_path / "storage"
    first = real_parent / "first"
    second = real_parent / "second"
    first.mkdir(parents=True)
    second.mkdir()
    alias_parent = tmp_path / "library-alias"
    _create_directory_symlink(alias_parent, real_parent)
    selected = alias_parent / "first"

    context = FolderContext.from_path(selected)
    sibling = sibling_context(context, 1)

    assert sibling is not None
    assert sibling.logical_path == alias_parent / "second"
    assert sibling.access_path == second.resolve()
    assert sibling_folder(selected, 1) == alias_parent / "second"


def test_single_archive_context_navigates_only_archive_peers(tmp_path: Path) -> None:
    archive_1 = tmp_path / "book1.zip"
    archive_2 = tmp_path / "book2.cbz"
    ignored_file = tmp_path / "notes.txt"
    child_folder = tmp_path / "folder"
    for path in (archive_1, archive_2, ignored_file):
        path.touch()
    child_folder.mkdir()

    sibling = sibling_context(FolderContext.from_path(archive_1), 1)

    assert sibling is not None
    assert sibling.logical_path == archive_2
    assert sibling.source_kind == "archive"


def test_sibling_folder_returns_none_without_another_folder(tmp_path: Path) -> None:
    only_folder = tmp_path / "only"
    only_folder.mkdir()

    assert sibling_folder(only_folder, 1) is None


def _create_directory_symlink(alias: Path, target: Path) -> None:
    try:
        alias.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlinks are unavailable: {error}")


def test_containing_folder_context_opens_archive_parent(tmp_path: Path) -> None:
    archive = tmp_path / "library" / "book.zip"
    archive.parent.mkdir()
    archive.write_bytes(b"zip")

    folder = containing_folder_context(FolderContext.from_path(archive))

    assert folder is not None
    assert folder.source_kind == "folder"
    assert folder.logical_path == archive.parent


def test_containing_folder_context_skips_folders_and_home(
    monkeypatch,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "book.zip"
    archive.write_bytes(b"zip")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert containing_folder_context(FolderContext.from_path(archive)) is None
    assert containing_folder_context(FolderContext.from_path(tmp_path)) is None
