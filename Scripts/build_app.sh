#!/usr/bin/env bash
# Build dist/ZipPictureViewer.app (and a zip) from the Swift package.
#   Scripts/build_app.sh [release|debug]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
CONFIGURATION="${1:-release}"
VERSION="$(tr -d '[:space:]' < VERSION)"
if [[ -z "${DEVELOPER_DIR:-}" && -d /Applications/Xcode.app ]]; then
  export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
fi

swift build -c "$CONFIGURATION"
BINARY="$(swift build -c "$CONFIGURATION" --show-bin-path)/ZipPictureViewer"

APP="dist/ZipPictureViewer.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BINARY" "$APP/Contents/MacOS/ZipPictureViewer"
cp assets/ZipPictureViewer.icns "$APP/Contents/Resources/ZipPictureViewer.icns"
sed "s/@VERSION@/$VERSION/g" Resources/Info.plist > "$APP/Contents/Info.plist"
plutil -lint "$APP/Contents/Info.plist" >/dev/null

# Ad-hoc signature for local use; release signing replaces it.
codesign --force --sign "${CODESIGN_IDENTITY:--}" "$APP"
codesign --verify --strict "$APP"

ARCHIVE="dist/ZipPictureViewer-v$VERSION-mac.zip"
rm -f "$ARCHIVE"
ditto -c -k --keepParent "$APP" "$ARCHIVE"
shasum -a 256 "$ARCHIVE" > "$ARCHIVE.sha256"
echo "Built $APP ($(du -sh "$APP" | cut -f1)) and $ARCHIVE"
