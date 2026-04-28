$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RootDir

$Version = "1.0.0"
$AppDir = Join-Path $RootDir "dist/ZipPictureViewer"
$Archive = Join-Path $RootDir "dist/ZipPictureViewer-v$Version-windows-x64.zip"

python scripts/generate_app_icon.py
python -m PyInstaller --noconfirm --clean ZipPictureViewer-windows.spec

$QtDir = Join-Path $AppDir "_internal/PySide6/Qt"
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
    "$QtDir/plugins/imageformats/qicns.dll",
    "$QtDir/plugins/imageformats/qico.dll",
    "$QtDir/plugins/imageformats/qpdf.dll",
    "$QtDir/plugins/imageformats/qsvg.dll",
    "$QtDir/plugins/imageformats/qtga.dll",
    "$QtDir/plugins/imageformats/qtiff.dll",
    "$QtDir/plugins/imageformats/qwbmp.dll"
)

foreach ($Path in $RemovePaths) {
    Remove-Item $Path -Recurse -Force -ErrorAction SilentlyContinue
}

if (Test-Path $Archive) {
    Remove-Item $Archive -Force
}
Compress-Archive -Path $AppDir -DestinationPath $Archive -Force

Write-Host "Built $AppDir"
Write-Host "Packed $Archive"
