from __future__ import annotations

import os
import shutil
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
from scripts.check_release_artifact import (
    check_checksum_sidecar,
    write_checksum_sidecar,
)
from scripts.check_release_version import (
    ReleaseVersionError,
    expected_release_tag,
    read_project_version,
    validate_release_tag,
    windows_version_tuple,
)
from scripts.generate_build_provenance import (
    BuildProvenanceError,
    DEPENDENCY_MANIFEST_FILENAME,
    check_distribution_metadata,
    validate_build_provenance,
    write_build_provenance,
)
from scripts.check_windows_bundle import (
    REQUIRED_BUNDLE_PATHS,
    check_archive,
    check_bundle_layout,
    expected_archive_name,
)
from scripts.benchmark_scan import benchmark


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_scan_benchmark_indexes_the_requested_corpus() -> None:
    metrics = benchmark(archives=3, images_per_archive=2)

    assert metrics["expected_images"] == 6
    assert metrics["indexed_images"] == 6
    assert metrics["issues"] == 0


def create_distribution_metadata(bundle_root: Path, version: str) -> Path:
    metadata_path = (
        bundle_root / "_internal" / f"zip_picture_viewer-{version}.dist-info" / "METADATA"
    )
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        f"Metadata-Version: 2.4\nName: zip-picture-viewer\nVersion: {version}\n",
        encoding="utf-8",
    )
    return metadata_path


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


def test_build_provenance_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    version = read_project_version(PROJECT_ROOT)
    provenance_dir = tmp_path / "release"
    commit_sha = "a" * 40

    metadata = write_build_provenance(
        provenance_dir,
        PROJECT_ROOT,
        commit_sha=commit_sha,
        dependencies=["pytest==8.3.5", "PySide6==6.8.3"],
        source_dirty=False,
        require_clean=True,
    )

    assert metadata["version"] == version
    assert metadata["commit_sha"] == commit_sha
    assert metadata["source_tree"] == "clean"
    assert (
        validate_build_provenance(
            provenance_dir,
            expected_version=version,
            expected_commit=commit_sha,
            require_clean=True,
        )
        == []
    )

    manifest = provenance_dir / DEPENDENCY_MANIFEST_FILENAME
    manifest.write_text(manifest.read_text(encoding="utf-8") + "tampered==1\n")
    errors = validate_build_provenance(
        provenance_dir,
        expected_version=version,
        expected_commit=commit_sha,
    )
    assert any("SHA-256" in error for error in errors)


def test_formal_provenance_rejects_dirty_source(tmp_path: Path) -> None:
    with pytest.raises(BuildProvenanceError, match="clean git worktree"):
        write_build_provenance(
            tmp_path,
            PROJECT_ROOT,
            commit_sha="b" * 40,
            dependencies=["PySide6==6.8.3"],
            source_dirty=True,
            require_clean=True,
        )


def test_distribution_metadata_version_is_validated(tmp_path: Path) -> None:
    version = read_project_version(PROJECT_ROOT)
    metadata_path = create_distribution_metadata(tmp_path, version)

    assert check_distribution_metadata(tmp_path, expected_version=version) == []

    metadata_path.write_text(
        "Metadata-Version: 2.4\nName: zip-picture-viewer\nVersion: 0.0.0\n",
        encoding="utf-8",
    )
    errors = check_distribution_metadata(tmp_path, expected_version=version)
    assert any("0.0.0" in error and version in error for error in errors)


def test_checksum_sidecar_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    archive = tmp_path / "release.zip"
    archive.write_bytes(b"release artifact")

    sidecar = write_checksum_sidecar(archive)

    assert check_checksum_sidecar(archive, sidecar) == []
    assert sidecar.read_text(encoding="utf-8").endswith("  release.zip\n")

    archive.write_bytes(b"tampered")
    assert any("Checksum mismatch" in error for error in check_checksum_sidecar(archive))


def test_windows_bundle_and_archive_checks(tmp_path: Path) -> None:
    version = read_project_version(PROJECT_ROOT)
    app_dir = tmp_path / "ZipPictureViewer"
    for relative_path in REQUIRED_BUNDLE_PATHS:
        bundle_file = app_dir / relative_path
        bundle_file.parent.mkdir(parents=True, exist_ok=True)
        bundle_file.write_bytes(b"test")
    metadata_path = create_distribution_metadata(app_dir, version)

    assert check_bundle_layout(app_dir) == []

    archive = tmp_path / expected_archive_name(version)
    with zipfile.ZipFile(archive, "w") as bundle_zip:
        for relative_path in REQUIRED_BUNDLE_PATHS:
            bundle_zip.write(
                app_dir / relative_path,
                f"{app_dir.name}/{relative_path}",
            )
        bundle_zip.write(
            metadata_path,
            f"{app_dir.name}/{metadata_path.relative_to(app_dir)}",
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
        ".github/workflows/macos-release.yml",
        ".github/workflows/packaging-ci.yml",
    )

    for relative_path in packaging_files:
        contents = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert version not in contents, relative_path

    mac_spec = (PROJECT_ROOT / "ZipPictureViewer.spec").read_text(encoding="utf-8")
    windows_spec = (PROJECT_ROOT / "ZipPictureViewer-windows.spec").read_text(encoding="utf-8")
    assert "read_project_version" in mac_spec
    assert "'CFBundleShortVersionString': APP_VERSION" in mac_spec
    assert "'LSMinimumSystemVersion': TARGET_MACOS_VERSION" in mac_spec
    assert "StringStruct('ProductVersion', APP_VERSION)" in windows_spec
    assert "version=VERSION_INFO" in windows_spec
    for spec in (mac_spec, windows_spec):
        assert "copy_metadata('zip-picture-viewer')" in spec
        assert "Path(entry).resolve() != PROJECT_ROOT" in spec
        assert "build-provenance.json" in spec
        assert "dependency-manifest.txt" in spec


def test_ci_checks_requested_tag_and_runs_tests_before_build() -> None:
    windows_release_workflow = (PROJECT_ROOT / ".github/workflows/windows-release.yml").read_text(
        encoding="utf-8"
    )
    macos_release_workflow = (PROJECT_ROOT / ".github/workflows/macos-release.yml").read_text(
        encoding="utf-8"
    )
    packaging_workflow = (PROJECT_ROOT / ".github/workflows/packaging-ci.yml").read_text(
        encoding="utf-8"
    )
    assert "scripts/benchmark_scan.py" in packaging_workflow
    assert "scan-benchmark-macos.json" in packaging_workflow
    assert "scan-benchmark-windows.json" in packaging_workflow

    assert "ref: ${{ inputs.tag_name }}" in windows_release_workflow
    assert "--tag $env:REQUESTED_TAG --verify-head" in windows_release_workflow
    assert windows_release_workflow.index("Run tests") < windows_release_workflow.index(
        "Build and validate Windows app"
    )
    assert "ref: ${{ inputs.tag_name }}" in macos_release_workflow
    assert '--tag "$REQUESTED_TAG" --verify-head' in macos_release_workflow
    assert macos_release_workflow.index("Run tests") < macos_release_workflow.index(
        "Build, sign, notarize, and validate macOS app"
    )
    for secret_name in (
        "MACOS_CERTIFICATE_BASE64",
        "MACOS_CERTIFICATE_PASSWORD",
        "MACOS_SIGNING_IDENTITY",
        "MACOS_NOTARY_APPLE_ID",
        "MACOS_NOTARY_TEAM_ID",
        "MACOS_NOTARY_PASSWORD",
    ):
        assert secret_name in macos_release_workflow
    assert "notarytool store-credentials" in macos_release_workflow
    assert 'REQUIRE_RELEASE_SIGNING: "1"' in macos_release_workflow
    assert ".sha256" in macos_release_workflow
    assert ".sha256" in windows_release_workflow
    assert packaging_workflow.count("Run tests") == 2
    assert packaging_workflow.count("-c constraints/packaging.txt") == 2
    assert packaging_workflow.index("Run tests") < packaging_workflow.index(
        "Build and validate macOS app"
    )


def test_build_scripts_run_packaged_smoke_test() -> None:
    mac_script = (PROJECT_ROOT / "scripts/build_macos_app.sh").read_text(encoding="utf-8")
    windows_script = (PROJECT_ROOT / "scripts/build_windows_app.ps1").read_text(encoding="utf-8")

    for script in (mac_script, windows_script):
        assert "--smoke-test" in script
        assert "ZIP_PICTURE_VIEWER_RUN_SMOKE_TEST" not in script

    assert 'TARGET_MACOS_VERSION="13.0"' in mac_script
    assert "check_macos_bundle.py" in mac_script
    assert "check_windows_bundle.py" in windows_script
    for script in (mac_script, windows_script):
        assert "generate_build_provenance.py" in script
        assert "--expected-commit" in script
        assert "check_release_artifact.py" in script
    assert "--require-developer-id" in mac_script
    assert "--require-notarized" in mac_script
    assert "slim-adhoc.zip" in mac_script
    assert "REQUIRE_RELEASE_SIGNING:-0" in mac_script


def test_formal_macos_build_fails_before_build_without_credentials() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is unavailable on this platform")

    env = os.environ.copy()
    env["REQUIRE_RELEASE_SIGNING"] = "1"
    env["PACKAGING_PYTHON"] = sys.executable
    env.pop("MACOS_SIGNING_IDENTITY", None)
    env.pop("NOTARYTOOL_PROFILE", None)

    result = subprocess.run(
        [bash, "scripts/build_macos_app.sh"],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Formal release requires MACOS_SIGNING_IDENTITY" in result.stderr
