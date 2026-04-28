from __future__ import annotations

from pathlib import Path

from .natural_sort import natural_sorted


def parent_folder(folder: Path) -> Path | None:
    resolved = _resolve(folder)
    parent = resolved.parent
    if parent == resolved or not parent.is_dir():
        return None
    return parent


def child_folders(folder: Path) -> list[Path]:
    try:
        children = [
            _resolve(path)
            for path in folder.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ]
    except OSError:
        return []

    return natural_sorted(children, key=lambda path: path.name)


def first_child_folder(folder: Path) -> Path | None:
    children = child_folders(folder)
    return children[0] if children else None


def sibling_folder(folder: Path, step: int) -> Path | None:
    resolved = _resolve(folder)
    parent = parent_folder(resolved)
    if parent is None:
        return None

    siblings = child_folders(parent)
    if len(siblings) <= 1:
        return None

    try:
        current_index = siblings.index(resolved)
    except ValueError:
        current_index = _find_same_folder_index(siblings, resolved)
        if current_index is None:
            return None

    return siblings[(current_index + step) % len(siblings)]


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _find_same_folder_index(folders: list[Path], target: Path) -> int | None:
    for index, folder in enumerate(folders):
        if _same_folder(folder, target):
            return index
    return None


def _same_folder(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return str(left).casefold() == str(right).casefold()
