#!/usr/bin/env python3
"""Validate the pruned, signed macOS application bundle."""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path

try:
    from .check_release_version import read_project_version
except ImportError:
    from check_release_version import read_project_version


MACHO_MAGICS = {
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf",
    b"\xbf\xba\xfe\xca",
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
}

REQUIRED_BUNDLE_PATHS = (
    "Contents/MacOS/ZipPictureViewer",
    "Contents/Frameworks/PySide6/Qt/plugins/platforms/libqcocoa.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/imageformats/libqgif.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/imageformats/libqjpeg.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/imageformats/libqwebp.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/styles/libqmacstyle.dylib",
)

FORBIDDEN_BUNDLE_PATHS = (
    "Contents/Frameworks/PySide6/Qt/plugins/generic",
    "Contents/Frameworks/PySide6/Qt/plugins/iconengines",
    "Contents/Frameworks/PySide6/Qt/plugins/platforminputcontexts",
    "Contents/Frameworks/PySide6/Qt/plugins/platforms/libqminimal.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/platforms/libqoffscreen.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/imageformats/libqicns.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/imageformats/libqico.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/imageformats/libqmacheif.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/imageformats/libqmacjp2.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/imageformats/libqpdf.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/imageformats/libqsvg.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/imageformats/libqtga.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/imageformats/libqtiff.dylib",
    "Contents/Frameworks/PySide6/Qt/plugins/imageformats/libqwbmp.dylib",
    "Contents/Frameworks/PySide6/Qt/lib/QtNetwork.framework",
    "Contents/Frameworks/PySide6/Qt/lib/QtOpenGL.framework",
    "Contents/Frameworks/PySide6/Qt/lib/QtPdf.framework",
    "Contents/Frameworks/PySide6/Qt/lib/QtQml.framework",
    "Contents/Frameworks/PySide6/Qt/lib/QtQmlMeta.framework",
    "Contents/Frameworks/PySide6/Qt/lib/QtQmlModels.framework",
    "Contents/Frameworks/PySide6/Qt/lib/QtQmlWorkerScript.framework",
    "Contents/Frameworks/PySide6/Qt/lib/QtQuick.framework",
    "Contents/Frameworks/PySide6/Qt/lib/QtSvg.framework",
    "Contents/Frameworks/PySide6/Qt/lib/QtVirtualKeyboard.framework",
    "Contents/Frameworks/PySide6/Qt/lib/QtVirtualKeyboardQml.framework",
)


def find_dangling_symlinks(app_dir: Path) -> list[Path]:
    return sorted(
        path for path in app_dir.rglob("*") if path.is_symlink() and not path.exists()
    )


def is_macho(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        with path.open("rb") as binary_file:
            return binary_file.read(4) in MACHO_MAGICS
    except OSError:
        return False


def find_macho_files(app_dir: Path) -> list[Path]:
    return sorted(path for path in app_dir.rglob("*") if is_macho(path))


def parse_minimum_macos_versions(otool_output: str) -> list[str]:
    versions: list[str] = []
    current_command: str | None = None

    for raw_line in otool_output.splitlines():
        line = raw_line.strip()
        if line.startswith("Load command "):
            current_command = None
        elif line.startswith("cmd "):
            current_command = line.removeprefix("cmd ").strip()
        elif current_command == "LC_BUILD_VERSION" and line.startswith("minos "):
            versions.append(line.removeprefix("minos ").strip())
        elif current_command == "LC_VERSION_MIN_MACOSX" and line.startswith("version "):
            versions.append(line.removeprefix("version ").strip())

    return versions


def macos_version_key(version: str) -> tuple[int, ...]:
    try:
        parts = tuple(int(part) for part in version.split("."))
    except ValueError as exc:
        raise ValueError(f"Invalid macOS version {version!r}") from exc
    return (*parts, *(0 for _ in range(max(0, 4 - len(parts)))))


def check_macho_minimum_versions(
    app_dir: Path, target_macos: str
) -> tuple[list[str], int]:
    errors: list[str] = []
    target_key = macos_version_key(target_macos)
    macho_files = find_macho_files(app_dir)

    for binary in macho_files:
        result = subprocess.run(
            ["otool", "-l", str(binary)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            errors.append(f"otool failed for {binary}: {result.stderr.strip()}")
            continue

        minimum_versions = parse_minimum_macos_versions(result.stdout)
        if not minimum_versions:
            errors.append(f"No macOS minimum version load command: {binary}")
            continue

        for minimum_version in minimum_versions:
            if macos_version_key(minimum_version) > target_key:
                relative_path = binary.relative_to(app_dir)
                errors.append(
                    f"{relative_path} requires macOS {minimum_version}, "
                    f"newer than target {target_macos}"
                )

    return errors, len(macho_files)


def check_bundle_metadata(
    app_dir: Path, expected_version: str, target_macos: str
) -> list[str]:
    info_path = app_dir / "Contents/Info.plist"
    try:
        with info_path.open("rb") as info_file:
            info = plistlib.load(info_file)
    except (OSError, plistlib.InvalidFileException) as exc:
        return [f"Cannot read {info_path}: {exc}"]

    errors: list[str] = []
    for key in ("CFBundleShortVersionString", "CFBundleVersion"):
        actual = info.get(key)
        if actual != expected_version:
            errors.append(f"{key} is {actual!r}; expected {expected_version!r}")
    minimum_system_version = info.get("LSMinimumSystemVersion")
    if minimum_system_version != target_macos:
        errors.append(
            f"LSMinimumSystemVersion is {minimum_system_version!r}; "
            f"expected {target_macos!r}"
        )
    return errors


def check_code_signature(app_dir: Path) -> list[str]:
    result = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app_dir)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return []
    details = result.stderr.strip() or result.stdout.strip()
    return [f"Code signature verification failed: {details}"]


def validate_bundle(
    app_dir: Path,
    project_root: Path,
    target_macos: str,
    verify_signature: bool = True,
) -> tuple[list[str], int]:
    if not app_dir.is_dir():
        return [f"Application bundle does not exist: {app_dir}"], 0

    errors: list[str] = []
    expected_version = read_project_version(project_root)
    errors.extend(check_bundle_metadata(app_dir, expected_version, target_macos))

    for relative_path in REQUIRED_BUNDLE_PATHS:
        if not (app_dir / relative_path).is_file():
            errors.append(f"Required bundle file is missing: {relative_path}")
    for relative_path in FORBIDDEN_BUNDLE_PATHS:
        if (app_dir / relative_path).exists():
            errors.append(f"Pruned bundle path is still present: {relative_path}")

    for symlink in find_dangling_symlinks(app_dir):
        errors.append(f"Dangling symlink: {symlink.relative_to(app_dir)} -> {symlink.readlink()}")

    minos_errors, macho_count = check_macho_minimum_versions(app_dir, target_macos)
    errors.extend(minos_errors)
    if verify_signature:
        errors.extend(check_code_signature(app_dir))
    return errors, macho_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app",
        type=Path,
        default=Path("dist/ZipPictureViewer.app"),
        help="application bundle to validate",
    )
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--target-macos", default="13.0")
    parser.add_argument("--skip-signature", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        errors, macho_count = validate_bundle(
            args.app.resolve(),
            args.project_root.resolve(),
            args.target_macos,
            verify_signature=not args.skip_signature,
        )
    except (OSError, ValueError) as exc:
        print(f"macOS bundle check failed: {exc}", file=sys.stderr)
        return 1

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        f"Validated {args.app}: {macho_count} Mach-O files support "
        f"macOS {args.target_macos}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
