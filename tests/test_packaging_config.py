from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.check_macos_bundle import (
    find_dangling_symlinks,
    macos_version_key,
    parse_minimum_macos_versions,
)
from scripts.check_release_version import (
    ReleaseVersionError,
    expected_release_tag,
    read_project_version,
    validate_release_tag,
    windows_version_tuple,
)
from scripts.check_windows_bundle import (
    REQUIRED_BUNDLE_PATHS,
    check_archive,
    check_bundle_layout,
    expected_archive_name,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_release_version_comes_from_pyproject() -> None:
    version = read_project_version(PROJECT_ROOT)

    result = subprocess.run(
        [sys.executable, "scripts/check_release_version.py"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == version
    assert expected_release_tag(version) == f"v{version}"
    validate_release_tag(f"v{version}", version)
    numeric_parts = tuple(int(part) for part in version.split("."))
    expected_windows_version = (*numeric_parts, *(0,) * (4 - len(numeric_parts)))
    assert windows_version_tuple(version) == expected_windows_version


def test_release_tag_must_match_project_version() -> None:
    version = read_project_version(PROJECT_ROOT)

    try:
        validate_release_tag("v999.999.999", version)
    except ReleaseVersionError as error:
        assert "does not match" in str(error)
    else:
        raise AssertionError("mismatched release tag was accepted")


def test_macos_minimum_version_parser_handles_both_load_commands() -> None:
    output = """
Load command 10
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform MACOS
    minos 13.0
Load command 11
      cmd LC_VERSION_MIN_MACOSX
  cmdsize 16
  version 10.13
      sdk 14.4
"""

    assert parse_minimum_macos_versions(output) == ["13.0", "10.13"]
    assert macos_version_key("13.0") > macos_version_key("12.6")


def test_macos_symlink_check_detects_only_dangling_links(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("ok", encoding="utf-8")
    good_link = tmp_path / "good"
    bad_link = tmp_path / "bad"
    try:
        good_link.symlink_to(target.name)
        bad_link.symlink_to("missing")
    except OSError as error:
        pytest.skip(f"File symlinks are unavailable: {error}")

    assert find_dangling_symlinks(tmp_path) == [bad_link]


def test_windows_bundle_and_archive_checks(tmp_path: Path) -> None:
    version = read_project_version(PROJECT_ROOT)
    app_dir = tmp_path / "ZipPictureViewer"
    for relative_path in REQUIRED_BUNDLE_PATHS:
        bundle_file = app_dir / relative_path
        bundle_file.parent.mkdir(parents=True, exist_ok=True)
        bundle_file.write_bytes(b"test")

    assert check_bundle_layout(app_dir) == []

    archive = tmp_path / expected_archive_name(version)
    with zipfile.ZipFile(archive, "w") as bundle_zip:
        for relative_path in REQUIRED_BUNDLE_PATHS:
            bundle_zip.write(
                app_dir / relative_path,
                f"{app_dir.name}/{relative_path}",
            )

    assert check_archive(archive, app_dir, version) == []


def test_packaging_files_do_not_embed_the_project_version() -> None:
    version = read_project_version(PROJECT_ROOT)
    packaging_files = (
        "ZipPictureViewer.spec",
        "ZipPictureViewer-windows.spec",
        "scripts/build_macos_app.sh",
        "scripts/build_windows_app.ps1",
        ".github/workflows/windows-release.yml",
        ".github/workflows/packaging-ci.yml",
    )

    for relative_path in packaging_files:
        contents = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert version not in contents, relative_path

    mac_spec = (PROJECT_ROOT / "ZipPictureViewer.spec").read_text(encoding="utf-8")
    windows_spec = (PROJECT_ROOT / "ZipPictureViewer-windows.spec").read_text(
        encoding="utf-8"
    )
    assert "read_project_version" in mac_spec
    assert "'CFBundleShortVersionString': APP_VERSION" in mac_spec
    assert "'LSMinimumSystemVersion': TARGET_MACOS_VERSION" in mac_spec
    assert "StringStruct('ProductVersion', APP_VERSION)" in windows_spec
    assert "version=VERSION_INFO" in windows_spec


def test_ci_checks_requested_tag_and_runs_tests_before_build() -> None:
    release_workflow = (
        PROJECT_ROOT / ".github/workflows/windows-release.yml"
    ).read_text(encoding="utf-8")
    packaging_workflow = (
        PROJECT_ROOT / ".github/workflows/packaging-ci.yml"
    ).read_text(encoding="utf-8")

    assert "ref: ${{ inputs.tag_name }}" in release_workflow
    assert "--tag $env:REQUESTED_TAG --verify-head" in release_workflow
    assert release_workflow.index("Run tests") < release_workflow.index(
        "Build and validate Windows app"
    )
    assert packaging_workflow.count("Run tests") == 2
    assert packaging_workflow.count("-c constraints/packaging.txt") == 2
    assert packaging_workflow.index("Run tests") < packaging_workflow.index(
        "Build and validate macOS app"
    )


def test_build_scripts_prepare_future_smoke_test_without_enabling_it() -> None:
    mac_script = (PROJECT_ROOT / "scripts/build_macos_app.sh").read_text(
        encoding="utf-8"
    )
    windows_script = (PROJECT_ROOT / "scripts/build_windows_app.ps1").read_text(
        encoding="utf-8"
    )

    for script in (mac_script, windows_script):
        assert "ZIP_PICTURE_VIEWER_RUN_SMOKE_TEST" in script
        assert "--smoke-test" in script

    assert 'TARGET_MACOS_VERSION="13.0"' in mac_script
    assert "check_macos_bundle.py" in mac_script
    assert "check_windows_bundle.py" in windows_script
