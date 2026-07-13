#!/usr/bin/env python3
"""Read the project version and validate release tags against it."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path


class ReleaseVersionError(ValueError):
    """Raised when release metadata is missing or inconsistent."""


ARTIFACT_VERSION_PATTERN = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]*")


def read_project_version(project_root: Path) -> str:
    pyproject_path = project_root / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as pyproject_file:
            project = tomllib.load(pyproject_file).get("project", {})
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseVersionError(f"Cannot read {pyproject_path}: {exc}") from exc

    version = project.get("version")
    if not isinstance(version, str) or not version or version != version.strip():
        raise ReleaseVersionError("[project].version must be a non-empty string")
    if ARTIFACT_VERSION_PATTERN.fullmatch(version) is None:
        raise ReleaseVersionError(
            f"[project].version contains unsafe artifact filename characters: {version!r}"
        )
    return version


def expected_release_tag(version: str) -> str:
    return f"v{version}"


def windows_version_tuple(version: str) -> tuple[int, int, int, int]:
    try:
        parts = [int(part) for part in version.split(".")]
    except ValueError as exc:
        raise ReleaseVersionError(
            f"Windows packaging requires a numeric dotted version, got {version!r}"
        ) from exc
    if not 1 <= len(parts) <= 4 or any(not 0 <= part <= 65_535 for part in parts):
        raise ReleaseVersionError(
            f"Windows packaging version must contain one to four 16-bit numbers: {version!r}"
        )
    return tuple([*parts, *([0] * (4 - len(parts)))])


def validate_release_tag(tag: str, version: str) -> None:
    expected = expected_release_tag(version)
    if tag != expected:
        raise ReleaseVersionError(
            f"Release tag {tag!r} does not match project version {version!r}; "
            f"expected {expected!r}"
        )


def verify_tag_points_to_head(project_root: Path, tag: str) -> None:
    head = _git_revision(project_root, "HEAD")
    tag_commit = _git_revision(project_root, f"refs/tags/{tag}^{{commit}}")
    if head != tag_commit:
        raise ReleaseVersionError(
            f"Checked-out commit {head} does not match tag {tag} ({tag_commit})"
        )


def _git_revision(project_root: Path, revision: str) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", revision],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseVersionError(f"Cannot resolve git revision {revision!r}") from exc
    return result.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository containing pyproject.toml",
    )
    parser.add_argument("--tag", help="release tag to compare with the project version")
    parser.add_argument(
        "--verify-head",
        action="store_true",
        help="also require the supplied tag to point at the checked-out commit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        version = read_project_version(args.project_root)
        if args.verify_head and not args.tag:
            raise ReleaseVersionError("--verify-head requires --tag")
        if args.tag:
            validate_release_tag(args.tag, version)
        if args.verify_head:
            verify_tag_points_to_head(args.project_root, args.tag)
    except ReleaseVersionError as exc:
        print(f"release version check failed: {exc}", file=sys.stderr)
        return 1

    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
