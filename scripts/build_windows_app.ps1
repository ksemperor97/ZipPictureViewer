$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RootDir

$VersionOutput = & python scripts/check_release_version.py
if ($LASTEXITCODE -ne 0) {
    throw "Could not determine the project version"
}
$Version = ([string]$VersionOutput).Trim()
if ([string]::IsNullOrWhiteSpace($Version)) {
    throw "Project version is empty"
}
$BuildCommitOutput = & git rev-parse --verify HEAD
if ($LASTEXITCODE -ne 0) {
    throw "Could not determine the build commit"
}
$BuildCommit = ([string]$BuildCommitOutput).Trim()

$AppDir = Join-Path $RootDir "dist/ZipPictureViewer"
$Archive = Join-Path $RootDir "dist/ZipPictureViewer-v$Version-windows-x64.zip"
$Checksum = "$Archive.sha256"

$ProvenanceArguments = @(
    "scripts/generate_build_provenance.py",
    "--project-root", $RootDir,
    "--output-dir", (Join-Path $RootDir "build/release-metadata")
)
if ($env:REQUIRE_CLEAN_PROVENANCE -eq "1") {
    $ProvenanceArguments += "--require-clean"
}
& python @ProvenanceArguments
if ($LASTEXITCODE -ne 0) {
    throw "Could not generate build provenance"
}

python scripts/generate_app_icon.py
python -m PyInstaller --noconfirm --clean ZipPictureViewer-windows.spec

$QtDir = Join-Path $AppDir "_internal/PySide6"
$RemovePaths = @(
    "$QtDir/translations",
    "$QtDir/qml",
    "$QtDir/plugins/tls",
    "$QtDir/plugins/bearer",
    "$QtDir/plugins/generic",
    "$QtDir/plugins/iconengines",
    "$QtDir/plugins/networkinformation",
    "$QtDir/plugins/platforminputcontexts",
    "$QtDir/plugins/printsupport",
    "$QtDir/plugins/qmltooling",
    "$QtDir/plugins/sqldrivers",
    "$QtDir/plugins/platforms/qminimal.dll",
    "$QtDir/plugins/platforms/qoffscreen.dll",
    "$QtDir/plugins/imageformats/qicns.dll",
    "$QtDir/plugins/imageformats/qico.dll",
    "$QtDir/plugins/imageformats/qpdf.dll",
    "$QtDir/plugins/imageformats/qsvg.dll",
    "$QtDir/plugins/imageformats/qtga.dll",
    "$QtDir/plugins/imageformats/qtiff.dll",
    "$QtDir/plugins/imageformats/qwbmp.dll"
)

foreach ($Path in $RemovePaths) {
    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
}

$ValidatorArguments = @(
    "scripts/check_windows_bundle.py",
    "--app-dir", $AppDir,
    "--expected-commit", $BuildCommit
)
if ($env:REQUIRE_CLEAN_PROVENANCE -eq "1") {
    $ValidatorArguments += "--require-clean-provenance"
}
if ($env:ZIP_PICTURE_VIEWER_REQUIRE_SIGNATURE -eq "1") {
    $ValidatorArguments += "--require-authenticode"
}
& python @ValidatorArguments
if ($LASTEXITCODE -ne 0) {
    throw "Windows bundle validation failed"
}

& (Join-Path $AppDir "ZipPictureViewer.exe") --smoke-test
if ($LASTEXITCODE -ne 0) {
    throw "Application smoke test failed"
}

if (Test-Path $Archive) {
    Remove-Item -LiteralPath $Archive -Force
}
if (Test-Path $Checksum) {
    Remove-Item -LiteralPath $Checksum -Force
}
Compress-Archive -Path $AppDir -DestinationPath $Archive -Force

$ArchiveValidatorArguments = $ValidatorArguments + @("--archive", $Archive)
& python @ArchiveValidatorArguments
if ($LASTEXITCODE -ne 0) {
    throw "Windows archive validation failed"
}
& python scripts/check_release_artifact.py --artifact $Archive --write
if ($LASTEXITCODE -ne 0) {
    throw "Windows archive checksum validation failed"
}

Write-Host "Built $AppDir"
Write-Host "Packed $Archive"
Write-Host "Checksum $Checksum"
