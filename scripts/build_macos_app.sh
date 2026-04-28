#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib:${DYLD_LIBRARY_PATH:-}"

python scripts/generate_app_icon.py
python -m PyInstaller --noconfirm --clean ZipPictureViewer.spec

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

codesign --force --deep --sign - "$APP_DIR" >/dev/null

echo "Built dist/ZipPictureViewer.app"
