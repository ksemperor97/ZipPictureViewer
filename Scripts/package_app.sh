#!/usr/bin/env bash
# Zip a built app bundle for distribution and write its SHA-256 checksum.
#   Scripts/package_app.sh [dist/ZipPictureViewer.app]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
APP="${1:-dist/ZipPictureViewer.app}"
VERSION="$(tr -d '[:space:]' < VERSION)"
ARCHIVE="dist/ZipPictureViewer-v$VERSION-mac.zip"

rm -f "$ARCHIVE" "$ARCHIVE.sha256"
ditto -c -k --keepParent "$APP" "$ARCHIVE"
# Relative name, so `shasum -c` works next to the downloaded zip.
(cd "$(dirname "$ARCHIVE")" && shasum -a 256 "$(basename "$ARCHIVE")" > "$(basename "$ARCHIVE").sha256")
echo "Built $APP ($(du -sh "$APP" | cut -f1)) and $ARCHIVE"
