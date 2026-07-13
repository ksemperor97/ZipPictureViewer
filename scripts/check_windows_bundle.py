#!/usr/bin/env python3
"""Validate the pruned Windows bundle and its release archive."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

try:
    from .check_release_version import read_project_version
    from .generate_build_provenance import (
        DEPENDENCY_MANIFEST_FILENAME,
        PROVENANCE_FILENAME,
        check_distribution_metadata,
        validate_build_provenance,
    )
except ImportError:
    from check_release_version import read_project_version
    from generate_build_provenance import (
        DEPENDENCY_MANIFEST_FILENAME,
        PROVENANCE_FILENAME,
        check_distribution_metadata,
        validate_build_provenance,
    )


REQUIRED_BUNDLE_PATHS = (
    "ZipPictureViewer.exe",
    f"_internal/release/{PROVENANCE_FILENAME}",
    f"_internal/release/{DEPENDENCY_MANIFEST_FILENAME}",
    "_internal/PySide6/Qt/plugins/platforms/qwindows.dll",
    "_internal/PySide6/Qt/plugins/imageformats/qgif.dll",
    "_internal/PySide6/Qt/plugins/imageformats/qjpeg.dll",
    "_internal/PySide6/Qt/plugins/imageformats/qwebp.dll",
)

FORBIDDEN_BUNDLE_PATHS = (
    "_internal/PySide6/Qt/translations",
    "_internal/PySide6/Qt/qml",
    "_internal/PySide6/Qt/plugins/tls",
    "_internal/PySide6/Qt/plugins/bearer",
    "_internal/PySide6/Qt/plugins/generic",
    "_internal/PySide6/Qt/plugins/iconengines",
    "_internal/PySide6/Qt/plugins/networkinformation",
    "_internal/PySide6/Qt/plugins/platforminputcontexts",
    "_internal/PySide6/Qt/plugins/printsupport",
    "_internal/PySide6/Qt/plugins/qmltooling",
    "_internal/PySide6/Qt/plugins/sqldrivers",
    "_internal/PySide6/Qt/plugins/platforms/qminimal.dll",
    "_internal/PySide6/Qt/plugins/platforms/qoffscreen.dll",
    "_internal/PySide6/Qt/plugins/imageformats/qicns.dll",
    "_internal/PySide6/Qt/plugins/imageformats/qico.dll",
    "_internal/PySide6/Qt/plugins/imageformats/qpdf.dll",
    "_internal/PySide6/Qt/plugins/imageformats/qsvg.dll",
    "_internal/PySide6/Qt/plugins/imageformats/qtga.dll",
    "_internal/PySide6/Qt/plugins/imageformats/qtiff.dll",
    "_internal/PySide6/Qt/plugins/imageformats/qwbmp.dll",
)


def expected_archive_name(version: str) -> str:
    return f"ZipPictureViewer-v{version}-windows-x64.zip"


def check_bundle_layout(app_dir: Path) -> list[str]:
    if not app_dir.is_dir():
        return [f"Application directory does not exist: {app_dir}"]

    errors: list[str] = []
    for relative_path in REQUIRED_BUNDLE_PATHS:
        if not (app_dir / relative_path).is_file():
            errors.append(f"Required bundle file is missing: {relative_path}")
    for relative_path in FORBIDDEN_BUNDLE_PATHS:
        if (app_dir / relative_path).exists():
            errors.append(f"Pruned bundle path is still present: {relative_path}")
    for path in app_dir.rglob("*"):
        if path.is_symlink():
            errors.append(f"Unexpected symlink in Windows bundle: {path.relative_to(app_dir)}")
    return errors


def check_archive(archive: Path, app_dir: Path, version: str) -> list[str]:
    expected_name = expected_archive_name(version)
    if archive.name != expected_name:
        return [f"Archive is named {archive.name!r}; expected {expected_name!r}"]
    if not archive.is_file():
        return [f"Archive does not exist: {archive}"]

    errors: list[str] = []
    try:
        with zipfile.ZipFile(archive) as bundle_zip:
            corrupt_member = bundle_zip.testzip()
            if corrupt_member:
                errors.append(f"Archive CRC check failed for {corrupt_member}")

            members = {item.filename.replace("\\", "/") for item in bundle_zip.infolist()}
            prefix = f"{app_dir.name}/"
            for relative_path in REQUIRED_BUNDLE_PATHS:
                if prefix + relative_path not in members:
                    errors.append(f"Archive is missing {prefix + relative_path}")
            metadata_prefix = prefix + "_internal/"
            if not any(
                member.startswith(metadata_prefix) and member.endswith(".dist-info/METADATA")
                for member in members
            ):
                errors.append("Archive is missing bundled distribution metadata")

            for item in bundle_zip.infolist():
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode):
                    errors.append(f"Unexpected symlink in archive: {item.filename}")
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"Cannot validate archive {archive}: {exc}")
    return errors


def check_authenticode(executable: Path) -> list[str]:
    status, error = _powershell_file_property(
        executable,
        "(Get-AuthenticodeSignature -LiteralPath $env:ZPV_EXECUTABLE).Status",
    )
    if status == "Valid":
        return []
    return [f"Authenticode signature is not valid: {status or error}"]


def check_product_version(executable: Path, expected_version: str) -> list[str]:
    version, error = _powershell_file_property(
        executable,
        "(Get-Item -LiteralPath $env:ZPV_EXECUTABLE).VersionInfo.ProductVersion",
    )
    if version == expected_version:
        return []
    details = f" ({error})" if error else ""
    return [f"Executable product version is {version!r}; expected {expected_version!r}{details}"]


def _powershell_file_property(executable: Path, expression: str) -> tuple[str, str]:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        return "", "PowerShell is unavailable"

    env = os.environ.copy()
    env["ZPV_EXECUTABLE"] = str(executable)
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-Command",
            expression,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        return "", result.stderr.strip()
    return result.stdout.strip(), ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, default=Path("dist/ZipPictureViewer"))
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--expected-commit")
    parser.add_argument("--require-clean-provenance", action="store_true")
    parser.add_argument("--require-authenticode", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version = read_project_version(args.project_root.resolve())
    app_dir = args.app_dir.resolve()
    errors = check_bundle_layout(app_dir)
    errors.extend(
        validate_build_provenance(
            app_dir / "_internal/release",
            expected_version=version,
            expected_commit=args.expected_commit,
            require_clean=args.require_clean_provenance,
        )
    )
    errors.extend(check_distribution_metadata(app_dir, expected_version=version))
    if os.name == "nt":
        errors.extend(check_product_version(app_dir / "ZipPictureViewer.exe", version))
    if args.archive:
        errors.extend(check_archive(args.archive.resolve(), app_dir, version))
    if args.require_authenticode:
        errors.extend(check_authenticode(app_dir / "ZipPictureViewer.exe"))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    suffix = f" and {args.archive}" if args.archive else ""
    print(f"Validated {args.app_dir}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
