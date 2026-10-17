from __future__ import annotations

from pathlib import Path

from .folder_context import ARCHIVE_EXTENSIONS, FolderContext
from .natural_sort import natural_sorted


NavigationSource = Path | FolderContext


def parent_folder(folder: NavigationSource) -> Path | None:
    logical_path = _logical_path(folder)
    parent = logical_path.parent
    if parent == logical_path or not parent.is_dir():
        return None
    return parent


def child_folders(folder: NavigationSource) -> list[Path]:
    logical_path = _logical_path(folder)
    try:
        children = [
            path
            for path in logical_path.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ]
    except OSError:
        return []

    return natural_sorted(children, key=lambda path: path.name)


def first_child_folder(folder: NavigationSource) -> Path | None:
    children = child_folders(folder)
    return children[0] if children else None


def sibling_folder(folder: NavigationSource, step: int) -> Path | None:
    """Return a sibling directory while retaining the selected path namespace."""

    logical_path = _logical_path(folder)
    parent = parent_folder(logical_path)
    if parent is None:
        return None

    siblings = child_folders(parent)
    return _stepped_sibling(logical_path, siblings, step)


def sibling_context(context: FolderContext, step: int) -> FolderContext | None:
    """Navigate peers appropriate for the selected source kind.

    Folder sources move between sibling folders. A directly opened archive
    moves between sibling ZIP/CBZ files without changing source kind.
    """

    parent = parent_folder(context)
    if parent is None:
        return None

    if context.source_kind == "archive":
        candidates = _child_archives(parent)
    else:
        candidates = child_folders(parent)

    sibling = _stepped_sibling(context.logical_path, candidates, step)
    if sibling is None:
        return None
    return FolderContext.from_path(sibling, context.source_kind)


def containing_folder_context(archive: FolderContext) -> FolderContext | None:
    """Return the folder to browse when the user opens a single archive.

    Opening one archive should expose its sibling archives as one continuous
    collection. The home directory and filesystem roots are excluded because
    a recursive scan there is slow and can trigger OS privacy prompts.
    """

    if archive.source_kind != "archive":
        return None
    parent = parent_folder(archive)
    if parent is None or _is_broad_scan_root(parent):
        return None
    return FolderContext.from_path(parent, "folder")


def _is_broad_scan_root(folder: Path) -> bool:
    return folder.parent == folder or folder.resolve() == Path.home().resolve()


def _child_archives(folder: Path) -> list[Path]:
    try:
        children = [
            path
            for path in folder.iterdir()
            if path.is_file()
            and not path.name.startswith(".")
            and path.suffix.casefold() in ARCHIVE_EXTENSIONS
        ]
    except OSError:
        return []
    return natural_sorted(children, key=lambda path: path.name)


def _logical_path(source: NavigationSource) -> Path:
    if isinstance(source, FolderContext):
        return source.logical_path
    return Path(source)


def _stepped_sibling(target: Path, siblings: list[Path], step: int) -> Path | None:
    if len(siblings) <= 1:
        return None

    current_index = _find_same_folder_index(siblings, target)
    if current_index is None:
        return None
    return siblings[(current_index + step) % len(siblings)]


def _find_same_folder_index(folders: list[Path], target: Path) -> int | None:
    for index, folder in enumerate(folders):
        if folder == target:
            return index
    for index, folder in enumerate(folders):
        if _same_folder(folder, target):
            return index
    return None


def _same_folder(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return str(left).casefold() == str(right).casefold()
