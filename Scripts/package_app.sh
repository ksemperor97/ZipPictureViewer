#!/usr/bin/env bash
# Zip a built app bundle for distribution.
#   Scripts/package_app.sh [dist/ZipPictureViewer.app]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
APP="${1:-dist/ZipPictureViewer.app}"
VERSION="$(tr -d '[:space:]' < VERSION)"
ARCHIVE="dist/ZipPictureViewer-v$VERSION-mac.zip"

rm -f "$ARCHIVE"
ditto -c -k --keepParent "$APP" "$ARCHIVE"
echo "Built $APP ($(du -sh "$APP" | cut -f1)) and $ARCHIVE"
