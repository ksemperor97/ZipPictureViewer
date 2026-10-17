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
FORMAL_RELEASE="${REQUIRE_RELEASE_SIGNING:-0}"
export MACOSX_DEPLOYMENT_TARGET="$TARGET_MACOS_VERSION"
TEMP_NOTARY_ARCHIVE=""

cleanup() {
  if [[ -n "$TEMP_NOTARY_ARCHIVE" ]]; then
    rm -f "$TEMP_NOTARY_ARCHIVE"
  fi
}
trap cleanup EXIT

if [[ "$FORMAL_RELEASE" != "0" && "$FORMAL_RELEASE" != "1" ]]; then
  echo "REQUIRE_RELEASE_SIGNING must be either 0 or 1" >&2
  exit 1
fi

if [[ "$FORMAL_RELEASE" == "1" ]]; then
  for variable_name in MACOS_SIGNING_IDENTITY NOTARYTOOL_PROFILE; do
    if [[ -z "${!variable_name:-}" ]]; then
      echo "Formal release requires $variable_name" >&2
      exit 1
    fi
  done
  if ! security find-identity -v -p codesigning | grep -Fq "$MACOS_SIGNING_IDENTITY"; then
    echo "Developer ID signing identity is unavailable: $MACOS_SIGNING_IDENTITY" >&2
    exit 1
  fi
fi

if [[ -d "/opt/homebrew/opt/expat/lib" ]]; then
  export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib:${DYLD_LIBRARY_PATH:-}"
elif [[ -d "/usr/local/opt/expat/lib" ]]; then
  export DYLD_LIBRARY_PATH="/usr/local/opt/expat/lib:${DYLD_LIBRARY_PATH:-}"
fi

VERSION="$("$PYTHON_BIN" scripts/check_release_version.py)"
BUILD_COMMIT_SHA="$(git rev-parse --verify HEAD)"
PROVENANCE_ARGUMENTS=(
  --project-root "$ROOT_DIR"
  --output-dir "$ROOT_DIR/build/release-metadata"
)
if [[ "$FORMAL_RELEASE" == "1" ]]; then
  PROVENANCE_ARGUMENTS+=(--require-clean)
fi
"$PYTHON_BIN" scripts/generate_build_provenance.py "${PROVENANCE_ARGUMENTS[@]}"

"$PYTHON_BIN" scripts/generate_app_icon.py
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean ZipPictureViewer.spec

APP_DIR="dist/ZipPictureViewer.app"
QT_DIR="$APP_DIR/Contents/Frameworks/PySide6/Qt"

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

VALIDATOR_ARGUMENTS=(
  --app "$APP_DIR"
  --target-macos "$TARGET_MACOS_VERSION"
  --expected-commit "$BUILD_COMMIT_SHA"
)
if [[ "$FORMAL_RELEASE" == "1" ]]; then
  codesign \
    --force \
    --deep \
    --options runtime \
    --timestamp \
    --sign "$MACOS_SIGNING_IDENTITY" \
    "$APP_DIR"
  VALIDATOR_ARGUMENTS+=(--require-clean-provenance --require-developer-id)
else
  codesign --force --deep --sign - "$APP_DIR" >/dev/null
fi
"$PYTHON_BIN" scripts/check_macos_bundle.py "${VALIDATOR_ARGUMENTS[@]}"

"$APP_DIR/Contents/MacOS/ZipPictureViewer" --smoke-test

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

if [[ "$FORMAL_RELEASE" == "1" ]]; then
  TEMP_NOTARY_ARCHIVE="dist/.ZipPictureViewer-v${VERSION}-notarization.zip"
  rm -f "$TEMP_NOTARY_ARCHIVE"
  ditto -c -k --sequesterRsrc --keepParent "$APP_DIR" "$TEMP_NOTARY_ARCHIVE"

  NOTARY_ARGUMENTS=(--keychain-profile "$NOTARYTOOL_PROFILE")
  if [[ -n "${NOTARYTOOL_KEYCHAIN:-}" ]]; then
    NOTARY_ARGUMENTS+=(--keychain "$NOTARYTOOL_KEYCHAIN")
  fi
  xcrun notarytool submit "$TEMP_NOTARY_ARCHIVE" "${NOTARY_ARGUMENTS[@]}" --wait
  rm -f "$TEMP_NOTARY_ARCHIVE"
  TEMP_NOTARY_ARCHIVE=""

  xcrun stapler staple "$APP_DIR"
  "$PYTHON_BIN" scripts/check_macos_bundle.py \
    "${VALIDATOR_ARGUMENTS[@]}" \
    --require-notarized
  ARCHIVE="dist/ZipPictureViewer-v${VERSION}-mac-${PACKAGE_ARCH}-slim.zip"
else
  ARCHIVE="dist/ZipPictureViewer-v${VERSION}-mac-${PACKAGE_ARCH}-slim-adhoc.zip"
fi

rm -f "$ARCHIVE" "$ARCHIVE.sha256"
ditto -c -k --sequesterRsrc --keepParent "$APP_DIR" "$ARCHIVE"
unzip -tq "$ARCHIVE" >/dev/null
"$PYTHON_BIN" scripts/check_release_artifact.py --artifact "$ARCHIVE" --write

echo "Built $APP_DIR"
echo "Packed $ARCHIVE"
echo "Checksum $ARCHIVE.sha256"
