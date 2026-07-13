#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -n "${PACKAGING_PYTHON:-}" ]]; then
  PYTHON_BIN="$PACKAGING_PYTHON"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3)"
fi

TARGET_MACOS_VERSION="13.0"
export MACOSX_DEPLOYMENT_TARGET="$TARGET_MACOS_VERSION"

if [[ -d "/opt/homebrew/opt/expat/lib" ]]; then
  export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib:${DYLD_LIBRARY_PATH:-}"
elif [[ -d "/usr/local/opt/expat/lib" ]]; then
  export DYLD_LIBRARY_PATH="/usr/local/opt/expat/lib:${DYLD_LIBRARY_PATH:-}"
fi

VERSION="$("$PYTHON_BIN" scripts/check_release_version.py)"

"$PYTHON_BIN" scripts/generate_app_icon.py
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean ZipPictureViewer.spec

APP_DIR="dist/ZipPictureViewer.app"
QT_DIR="$APP_DIR/Contents/Frameworks/PySide6/Qt"
PYSIDE_DIR="$APP_DIR/Contents/Frameworks/PySide6"

rm -rf \
  "$QT_DIR/lib/QtNetwork.framework" \
  "$QT_DIR/lib/QtOpenGL.framework" \
  "$QT_DIR/lib/QtPdf.framework" \
  "$QT_DIR/lib/QtQml.framework" \
  "$QT_DIR/lib/QtQmlMeta.framework" \
  "$QT_DIR/lib/QtQmlModels.framework" \
  "$QT_DIR/lib/QtQmlWorkerScript.framework" \
  "$QT_DIR/lib/QtQuick.framework" \
  "$QT_DIR/lib/QtSvg.framework" \
  "$QT_DIR/lib/QtVirtualKeyboard.framework" \
  "$QT_DIR/lib/QtVirtualKeyboardQml.framework" \
  "$QT_DIR/plugins/generic" \
  "$QT_DIR/plugins/iconengines" \
  "$QT_DIR/plugins/platforminputcontexts" \
  "$QT_DIR/plugins/platforms/libqminimal.dylib" \
  "$QT_DIR/plugins/platforms/libqoffscreen.dylib" \
  "$QT_DIR/plugins/imageformats/libqicns.dylib" \
  "$QT_DIR/plugins/imageformats/libqico.dylib" \
  "$QT_DIR/plugins/imageformats/libqmacheif.dylib" \
  "$QT_DIR/plugins/imageformats/libqmacjp2.dylib" \
  "$QT_DIR/plugins/imageformats/libqpdf.dylib" \
  "$QT_DIR/plugins/imageformats/libqsvg.dylib" \
  "$QT_DIR/plugins/imageformats/libqtga.dylib" \
  "$QT_DIR/plugins/imageformats/libqtiff.dylib" \
  "$QT_DIR/plugins/imageformats/libqwbmp.dylib"

while IFS= read -r -d '' symlink; do
  if [[ ! -e "$symlink" ]]; then
    rm -- "$symlink"
  fi
done < <(find "$APP_DIR" -type l -print0)

codesign --force --deep --sign - "$APP_DIR" >/dev/null
"$PYTHON_BIN" scripts/check_macos_bundle.py \
  --app "$APP_DIR" \
  --target-macos "$TARGET_MACOS_VERSION"

if [[ "${ZIP_PICTURE_VIEWER_RUN_SMOKE_TEST:-0}" == "1" ]]; then
  "$APP_DIR/Contents/MacOS/ZipPictureViewer" --smoke-test
fi

ARCHITECTURES="$(lipo -archs "$APP_DIR/Contents/MacOS/ZipPictureViewer")"
if [[ "$ARCHITECTURES" == "arm64" ]]; then
  PACKAGE_ARCH="arm64"
elif [[ "$ARCHITECTURES" == "x86_64" ]]; then
  PACKAGE_ARCH="x64"
elif [[ " $ARCHITECTURES " == *" arm64 "* && " $ARCHITECTURES " == *" x86_64 "* ]]; then
  PACKAGE_ARCH="universal2"
else
  echo "Unsupported macOS application architecture: $ARCHITECTURES" >&2
  exit 1
fi

ARCHIVE="dist/ZipPictureViewer-v${VERSION}-mac-${PACKAGE_ARCH}-slim.zip"
rm -f "$ARCHIVE"
ditto -c -k --sequesterRsrc --keepParent "$APP_DIR" "$ARCHIVE"
unzip -tq "$ARCHIVE" >/dev/null

echo "Built $APP_DIR"
echo "Packed $ARCHIVE"
