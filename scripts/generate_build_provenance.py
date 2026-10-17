#!/usr/bin/env python3
"""Generate and validate immutable build provenance bundled with releases."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
from email.parser import BytesParser
from pathlib import Path
from typing import Iterable

try:
    from .check_release_version import read_project_version
except ImportError:
    from check_release_version import read_project_version


PROVENANCE_FILENAME = "build-provenance.json"
DEPENDENCY_MANIFEST_FILENAME = "dependency-manifest.txt"
PROVENANCE_SCHEMA_VERSION = 1
PROJECT_DISTRIBUTION = "zip-picture-viewer"
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40,64}")


class BuildProvenanceError(ValueError):
    """Raised when build provenance cannot be generated safely."""


def canonical_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def resolve_git_commit(project_root: Path) -> str:
    return _git_output(project_root, "rev-parse", "--verify", "HEAD")


def source_tree_is_dirty(project_root: Path) -> bool:
    return bool(
        _git_output(
            project_root,
            "status",
            "--porcelain",
            "--untracked-files=normal",
        )
    )


def installed_dependency_lines() -> list[str]:
    dependencies: set[str] = set()
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if not name or not version:
            continue
        dependencies.add(f"{canonical_distribution_name(name)}=={version}")
    if not dependencies:
        raise BuildProvenanceError("No installed Python distributions were found")
    return sorted(dependencies, key=str.casefold)


def write_build_provenance(
    output_dir: Path,
    project_root: Path,
    *,
    commit_sha: str | None = None,
    dependencies: Iterable[str] | None = None,
    source_dirty: bool | None = None,
    require_clean: bool = False,
) -> dict[str, object]:
    project_root = project_root.resolve()
    output_dir = output_dir.resolve()
    commit_sha = commit_sha or resolve_git_commit(project_root)
    if COMMIT_PATTERN.fullmatch(commit_sha) is None:
        raise BuildProvenanceError(f"Invalid git commit SHA: {commit_sha!r}")

    dirty = source_tree_is_dirty(project_root) if source_dirty is None else source_dirty
    if require_clean and dirty:
        raise BuildProvenanceError("Formal release builds require a clean git worktree and index")

    dependency_lines = sorted(
        {line.strip() for line in (dependencies or installed_dependency_lines()) if line.strip()},
        key=str.casefold,
    )
    if not dependency_lines:
        raise BuildProvenanceError("Dependency manifest cannot be empty")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_text = "\n".join(dependency_lines) + "\n"
    manifest_path = output_dir / DEPENDENCY_MANIFEST_FILENAME
    manifest_path.write_text(manifest_text, encoding="utf-8", newline="\n")

    metadata: dict[str, object] = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "distribution": PROJECT_DISTRIBUTION,
        "version": read_project_version(project_root),
        "commit_sha": commit_sha,
        "source_tree": "dirty" if dirty else "clean",
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "dependency_manifest": DEPENDENCY_MANIFEST_FILENAME,
        "dependency_count": len(dependency_lines),
        "dependency_manifest_sha256": hashlib.sha256(manifest_text.encode("utf-8")).hexdigest(),
    }
    provenance_path = output_dir / PROVENANCE_FILENAME
    provenance_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return metadata


def validate_build_provenance(
    provenance_dir: Path,
    *,
    expected_version: str,
    expected_commit: str | None = None,
    require_clean: bool = False,
) -> list[str]:
    provenance_path = provenance_dir / PROVENANCE_FILENAME
    manifest_path = provenance_dir / DEPENDENCY_MANIFEST_FILENAME
    errors: list[str] = []

    try:
        metadata = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Cannot read build provenance {provenance_path}: {exc}"]
    if not isinstance(metadata, dict):
        return [f"Build provenance must be a JSON object: {provenance_path}"]

    expected_values = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "distribution": PROJECT_DISTRIBUTION,
        "version": expected_version,
        "dependency_manifest": DEPENDENCY_MANIFEST_FILENAME,
    }
    for key, expected in expected_values.items():
        if metadata.get(key) != expected:
            errors.append(f"Build provenance {key} is {metadata.get(key)!r}; expected {expected!r}")

    commit_sha = metadata.get("commit_sha")
    if not isinstance(commit_sha, str) or COMMIT_PATTERN.fullmatch(commit_sha) is None:
        errors.append(f"Build provenance commit_sha is invalid: {commit_sha!r}")
    elif expected_commit is not None and commit_sha != expected_commit:
        errors.append(f"Build provenance commit {commit_sha} does not match {expected_commit}")

    source_tree = metadata.get("source_tree")
    if source_tree not in ("clean", "dirty"):
        errors.append(f"Build provenance source_tree is invalid: {source_tree!r}")
    elif require_clean and source_tree != "clean":
        errors.append("Formal release provenance reports a dirty source tree")

    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"Cannot read dependency manifest {manifest_path}: {exc}")
        return errors

    dependency_lines = [line for line in manifest_text.splitlines() if line]
    if not dependency_lines:
        errors.append("Dependency manifest is empty")
    if dependency_lines != sorted(set(dependency_lines), key=str.casefold):
        errors.append("Dependency manifest entries are not unique and sorted")
    if metadata.get("dependency_count") != len(dependency_lines):
        errors.append("Build provenance dependency_count does not match the manifest")
    actual_hash = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    if metadata.get("dependency_manifest_sha256") != actual_hash:
        errors.append("Dependency manifest SHA-256 does not match build provenance")
    return errors


def check_distribution_metadata(
    bundle_root: Path,
    *,
    expected_version: str,
    distribution_name: str = PROJECT_DISTRIBUTION,
) -> list[str]:
    expected_name = canonical_distribution_name(distribution_name)
    matches: list[tuple[Path, str | None]] = []
    for metadata_path in bundle_root.rglob("*.dist-info/METADATA"):
        try:
            with metadata_path.open("rb") as metadata_file:
                metadata = BytesParser().parse(metadata_file, headersonly=True)
        except OSError:
            continue
        name = metadata.get("Name")
        if isinstance(name, str) and canonical_distribution_name(name) == expected_name:
            matches.append((metadata_path, metadata.get("Version")))

    if not matches:
        return [f"Bundled distribution metadata for {distribution_name!r} was not found"]
    errors: list[str] = []
    for metadata_path, version in matches:
        if version != expected_version:
            errors.append(
                f"{metadata_path.relative_to(bundle_root)} version is {version!r}; "
                f"expected {expected_version!r}"
            )
    return errors


def _git_output(project_root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BuildProvenanceError(
            f"Cannot run git {' '.join(arguments)} in {project_root}"
        ) from exc
    return result.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/release-metadata"),
    )
    parser.add_argument("--require-clean", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        metadata = write_build_provenance(
            args.output_dir,
            args.project_root,
            require_clean=args.require_clean,
        )
    except BuildProvenanceError as exc:
        print(f"build provenance generation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Generated {args.output_dir} for {metadata['commit_sha']} ({metadata['source_tree']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
