#!/bin/bash
set -euo pipefail

# HV P2P SRVR macOS Developer ID signing + Apple notarisation.
#
# Required signing identity:
#   APPLE_SIGN_IDENTITY="Developer ID Application: ..."
#
# Preferred notarisation authentication (GitHub Actions / App Store Connect API key):
#   APPLE_NOTARY_KEY_PATH=/path/AuthKey_XXXXXXXXXX.p8
#   APPLE_NOTARY_KEY_ID=XXXXXXXXXX
#   APPLE_NOTARY_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
#
# Local alternatives are also supported:
#   NOTARY_KEYCHAIN_PROFILE=HV-P2P-NOTARY
# or APPLE_ID + APPLE_APP_PASSWORD + APPLE_TEAM_ID.

APP="${1:-}"
if [ -z "$APP" ] || [ ! -d "$APP" ]; then
  echo "Usage: $0 '/path/HV P2P SRVR v26.08.15.07.app'" >&2
  exit 2
fi

IDENTITY="${APPLE_SIGN_IDENTITY:-}"
if [ -z "$IDENTITY" ]; then
  IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | sed -n 's/.*"\(Developer ID Application:[^"]*\)".*/\1/p' | head -n 1)"
fi
if [ -z "$IDENTITY" ]; then
  echo "No Developer ID Application signing identity was found." >&2
  exit 3
fi

echo "Signing application with: $IDENTITY"

# pyside6-deploy/Nuitka produces a self-contained Qt application. --deep is
# intentional for this generated bundle so all nested Qt/Python code is
# re-signed consistently with Developer ID + Hardened Runtime.
codesign --force --deep --options runtime --timestamp --sign "$IDENTITY" "$APP"

printf '\nVerifying Developer ID signature...\n'
codesign --verify --deep --strict --verbose=4 "$APP"
codesign -dv --verbose=4 "$APP" 2>&1 | sed -n '1,80p'

NOTARY_ZIP="${APP%.app}-notarize.zip"
RESULT_JSON="${TMPDIR:-/tmp}/hv-p2p-notary-result.json"
LOG_JSON="${TMPDIR:-/tmp}/hv-p2p-notary-log.json"
rm -f "$NOTARY_ZIP" "$RESULT_JSON" "$LOG_JSON"
ditto -c -k --keepParent "$APP" "$NOTARY_ZIP"

printf '\nSubmitting to Apple notarisation service...\n'
set +e
if [ -n "${APPLE_NOTARY_KEY_PATH:-}" ] && [ -n "${APPLE_NOTARY_KEY_ID:-}" ] && [ -n "${APPLE_NOTARY_ISSUER_ID:-}" ]; then
  xcrun notarytool submit "$NOTARY_ZIP" \
    --key "$APPLE_NOTARY_KEY_PATH" \
    --key-id "$APPLE_NOTARY_KEY_ID" \
    --issuer "$APPLE_NOTARY_ISSUER_ID" \
    --wait --output-format json | tee "$RESULT_JSON"
  NOTARY_RC=${PIPESTATUS[0]}
elif [ -n "${NOTARY_KEYCHAIN_PROFILE:-}" ]; then
  xcrun notarytool submit "$NOTARY_ZIP" \
    --keychain-profile "$NOTARY_KEYCHAIN_PROFILE" \
    --wait --output-format json | tee "$RESULT_JSON"
  NOTARY_RC=${PIPESTATUS[0]}
else
  : "${APPLE_ID:?Set App Store Connect API key variables, NOTARY_KEYCHAIN_PROFILE, or APPLE_ID}"
  : "${APPLE_APP_PASSWORD:?Set APPLE_APP_PASSWORD}"
  : "${APPLE_TEAM_ID:?Set APPLE_TEAM_ID}"
  xcrun notarytool submit "$NOTARY_ZIP" \
    --apple-id "$APPLE_ID" \
    --password "$APPLE_APP_PASSWORD" \
    --team-id "$APPLE_TEAM_ID" \
    --wait --output-format json | tee "$RESULT_JSON"
  NOTARY_RC=${PIPESTATUS[0]}
fi
set -e

SUBMISSION_ID="$(python3 - "$RESULT_JSON" <<'PY'
import json, sys
try:
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        d = json.load(f)
    print(d.get('id', '') or '')
except Exception:
    print('')
PY
)"
NOTARY_STATUS="$(python3 - "$RESULT_JSON" <<'PY'
import json, sys
try:
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        d = json.load(f)
    print(d.get('status', '') or '')
except Exception:
    print('')
PY
)"

if [ "$NOTARY_RC" -ne 0 ] || [ "$NOTARY_STATUS" != "Accepted" ]; then
  echo "Notarisation did not complete successfully. Status: ${NOTARY_STATUS:-unknown}; submission: ${SUBMISSION_ID:-unknown}" >&2
  if [ -n "$SUBMISSION_ID" ] && [ -n "${APPLE_NOTARY_KEY_PATH:-}" ]; then
    xcrun notarytool log "$SUBMISSION_ID" \
      --key "$APPLE_NOTARY_KEY_PATH" \
      --key-id "$APPLE_NOTARY_KEY_ID" \
      --issuer "$APPLE_NOTARY_ISSUER_ID" \
      "$LOG_JSON" || true
    if [ -f "$LOG_JSON" ]; then
      echo "---- Apple notarisation log ----" >&2
      cat "$LOG_JSON" >&2
    fi
  fi
  exit 4
fi

printf '\nStapling Apple notarisation ticket...\n'
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"

printf '\nGatekeeper assessment...\n'
spctl --assess --type execute --verbose=4 "$APP"

rm -f "$NOTARY_ZIP"
echo "Signed, notarised and stapled successfully: $APP"
