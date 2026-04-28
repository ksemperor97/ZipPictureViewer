from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile, ZipFile

from .models import ImageEntry
from .natural_sort import natural_sorted


ARCHIVE_EXTENSIONS = {".cbz", ".zip"}
IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}


def find_archives(root: Path) -> list[Path]:
    archives = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.casefold() in ARCHIVE_EXTENSIONS
    ]
    return natural_sorted(archives, key=lambda path: path.relative_to(root))


def find_image_folders(root: Path) -> list[Path]:
    folders = [
        path
        for path in [root, *root.rglob("*")]
        if path.is_dir() and image_members_in_folder(path)
    ]
    return natural_sorted(folders, key=lambda path: path.relative_to(root))


def find_image_containers(root: Path) -> list[Path]:
    containers = [*find_archives(root), *find_image_folders(root)]
    return natural_sorted(containers, key=lambda path: path.relative_to(root))


def image_members_in_archive(archive_path: Path) -> list[str]:
    try:
        with ZipFile(archive_path) as archive:
            members = [
                info.filename
                for info in archive.infolist()
                if not info.is_dir() and _is_image_member(info.filename)
            ]
    except BadZipFile:
        return []

    return natural_sorted(members)


def image_members_in_folder(folder_path: Path) -> list[str]:
    try:
        members = [
            path.name
            for path in folder_path.iterdir()
            if path.is_file() and _is_image_member(path.name)
        ]
    except OSError:
        return []

    return natural_sorted(members)


def build_image_index(root: Path) -> list[ImageEntry]:
    entries: list[ImageEntry] = []
    for archive_path in find_image_containers(root):
        if archive_path.is_dir():
            members = image_members_in_folder(archive_path)
        else:
            members = image_members_in_archive(archive_path)

        entries.extend(
            ImageEntry(archive_path=archive_path, member_name=member_name)
            for member_name in members
        )
    return entries


def _is_image_member(member_name: str) -> bool:
    path = Path(member_name)
    if any(part.startswith("__MACOSX") for part in path.parts):
        return False
    if path.name.startswith("."):
        return False
    return path.suffix.casefold() in IMAGE_EXTENSIONS
