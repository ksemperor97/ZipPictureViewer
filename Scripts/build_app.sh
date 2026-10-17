#!/usr/bin/env bash
# Build dist/ZipPictureViewer.app (and a zip) from the Swift package.
#   Scripts/build_app.sh [release|debug]
#
# Environment:
#   ARCHS                   architectures to build (default "arm64 x86_64", a universal binary)
#   CODESIGN_IDENTITY       signing identity; unset or "-" signs ad-hoc for local use
#   REQUIRE_RELEASE_SIGNING set to 1 to refuse an ad-hoc signature
#   NOTARYTOOL_PROFILE      notarize, staple and re-package via Scripts/notarize_app.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
CONFIGURATION="${1:-release}"
ARCHS="${ARCHS:-arm64 x86_64}"
IDENTITY="${CODESIGN_IDENTITY:--}"
APP="dist/ZipPictureViewer.app"
# Multi-architecture `swift build` needs Xcode's build system, not the Command Line Tools.
if [[ -z "${DEVELOPER_DIR:-}" && -d /Applications/Xcode.app ]]; then
  export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
fi

build_binary() {
  local arch_flags=()
  local arch
  for arch in $ARCHS; do
    arch_flags+=(--arch "$arch")
  done
  swift build -c "$CONFIGURATION" "${arch_flags[@]}"
  BINARY="$(swift build -c "$CONFIGURATION" "${arch_flags[@]}" --show-bin-path)/ZipPictureViewer"
}

assemble_bundle() {
  local version
  version="$(tr -d '[:space:]' < VERSION)"
  rm -rf "$APP"
  mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
  cp "$BINARY" "$APP/Contents/MacOS/ZipPictureViewer"
  cp assets/ZipPictureViewer.icns "$APP/Contents/Resources/ZipPictureViewer.icns"
  sed "s/@VERSION@/$version/g" Resources/Info.plist > "$APP/Contents/Info.plist"
  plutil -lint "$APP/Contents/Info.plist" >/dev/null
}

# Each requested slice must be present, and each must load on the oldest macOS
# the Info.plist promises; otherwise Finder would offer an app that cannot launch.
verify_binary() {
  local executable="$APP/Contents/MacOS/ZipPictureViewer"
  local minimum arch minos
  minimum="$(plutil -extract LSMinimumSystemVersion raw "$APP/Contents/Info.plist")"
  for arch in $ARCHS; do
    if ! lipo "$executable" -verify_arch "$arch"; then
      echo "Missing $arch slice in $executable ($(lipo -archs "$executable"))" >&2
      exit 1
    fi
    minos="$(vtool -arch "$arch" -show-build "$executable" | awk '$1 == "minos" { print $2 }')"
    if [[ "$minos" != "$minimum" ]]; then
      echo "$arch slice targets macOS $minos, but LSMinimumSystemVersion is $minimum" >&2
      exit 1
    fi
  done
  echo "Binary slices: $(lipo -archs "$executable") (minos $minimum)"
}

sign_bundle() {
  if [[ "$IDENTITY" == "-" ]]; then
    if [[ "${REQUIRE_RELEASE_SIGNING:-0}" == "1" ]]; then
      echo "REQUIRE_RELEASE_SIGNING=1 but CODESIGN_IDENTITY is not set" >&2
      exit 1
    fi
    # Ad-hoc signatures cannot be timestamped; the hardened runtime still applies,
    # so local runs behave like the notarized release.
    codesign --force --options runtime --sign - "$APP"
  else
    codesign --force --options runtime --timestamp --sign "$IDENTITY" "$APP"
  fi
  codesign --verify --strict --verbose=2 "$APP"
}

build_binary
assemble_bundle
verify_binary
sign_bundle
if [[ -n "${NOTARYTOOL_PROFILE:-}" ]]; then
  Scripts/notarize_app.sh "$APP"
else
  Scripts/package_app.sh "$APP"
fi
