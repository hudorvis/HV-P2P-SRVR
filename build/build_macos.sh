#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/source"
DIST="$ROOT/dist-macos"
VENV="$ROOT/.build-venv-macos"
VERSION="v26.08.15.05"
APP_NAME="HV P2P SRVR"

printf '\nHV P2P SRVR %s — macOS Qt/QML build\n' "$VERSION"
printf 'Host Python: '
python3 --version
printf '\n'

rm -rf "$DIST"
# Use a fresh build environment so a previous Qt/Nuitka deployment cannot
# contaminate this revision.
rm -rf "$VENV"
python3 -m venv "$VENV"
source "$VENV/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$SRC/requirements.txt"

# Basic Python source validation. Do NOT call `pyside6-project qmllint` here.
# That project command invokes pyside6-metaobjectdump, which is intended for
# Python QML type registration and can reject valid context-property bridge
# declarations such as Property("QVariantMap", ...). Our bridge is exposed to
# QML with QQmlContext.setContextProperty(), so that pass is not required.
python -m py_compile \
  "$SRC/main.py" \
  "$SRC/bridge.py" \
  "$SRC/backend_worker.py" \
  "$SRC/hv_p2p_legacy_core.py"

cd "$SRC"
rm -f pysidedeploy.spec

printf '\nBuilding self-contained Qt application with pyside6-deploy...\n\n'
pyside6-deploy main.py --force --name "$APP_NAME"

APP="$(find "$SRC" -maxdepth 5 -type d -name "$APP_NAME.app" -print -quit)"
if [ -z "$APP" ]; then
  APP="$(find "$SRC" -maxdepth 5 -type d -name '*.app' -print -quit)"
fi
if [ -z "$APP" ]; then
  echo "Build completed but no .app bundle was found." >&2
  exit 2
fi

mkdir -p "$DIST"
cp -R "$APP" "$DIST/HV P2P SRVR $VERSION.app"

printf '\nBuilt successfully:\n%s\n\n' "$DIST/HV P2P SRVR $VERSION.app"
printf 'The application is self-contained; the build virtual environment is not required to run it.\n'
