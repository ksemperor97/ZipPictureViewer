#!/usr/bin/env bash
# Notarize a Developer ID–signed app, staple the ticket, check Gatekeeper, and re-package it.
#   NOTARYTOOL_PROFILE=<profile> Scripts/notarize_app.sh [dist/ZipPictureViewer.app]
#
# Environment:
#   NOTARYTOOL_PROFILE   keychain profile created with `xcrun notarytool store-credentials`
#   NOTARYTOOL_KEYCHAIN  keychain holding that profile (default: the login keychain)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
APP="${1:-dist/ZipPictureViewer.app}"
PROFILE="${NOTARYTOOL_PROFILE:?set NOTARYTOOL_PROFILE to a notarytool keychain profile}"
if [[ -z "${DEVELOPER_DIR:-}" && -d /Applications/Xcode.app ]]; then
  export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
fi
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# Apple rejects ad-hoc signatures and binaries without the hardened runtime;
# failing here is quicker than waiting for the notary service to say so.
check_signature() {
  local details
  details="$(codesign --display --verbose=2 "$APP" 2>&1)"
  if grep -q "Signature=adhoc" <<<"$details"; then
    echo "$APP is signed ad-hoc; rebuild with CODESIGN_IDENTITY set to a Developer ID" >&2
    exit 1
  fi
  if ! grep -Eq "flags=.*runtime" <<<"$details"; then
    echo "$APP is not signed with the hardened runtime" >&2
    exit 1
  fi
}

submit() {
  local upload="$WORK_DIR/upload.zip"
  local result="$WORK_DIR/result.json"
  local keychain_args=()
  if [[ -n "${NOTARYTOOL_KEYCHAIN:-}" ]]; then
    keychain_args=(--keychain "$NOTARYTOOL_KEYCHAIN")
  fi
  ditto -c -k --keepParent "$APP" "$upload"
  # notarytool exits 0 for a finished but rejected submission, so read the status.
  xcrun notarytool submit "$upload" --keychain-profile "$PROFILE" ${keychain_args[@]+"${keychain_args[@]}"} \
    --wait --output-format json > "$result"
  local status submission_id
  status="$(plutil -extract status raw "$result")"
  submission_id="$(plutil -extract id raw "$result")"
  echo "Notarization $submission_id: $status"
  if [[ "$status" != "Accepted" ]]; then
    xcrun notarytool log "$submission_id" --keychain-profile "$PROFILE" ${keychain_args[@]+"${keychain_args[@]}"} >&2 || true
    exit 1
  fi
}

check_signature
submit
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"
spctl --assess --type execute -vv "$APP"
Scripts/package_app.sh "$APP"
