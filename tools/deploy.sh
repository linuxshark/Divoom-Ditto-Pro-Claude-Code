#!/bin/sh
# Deploy a self-contained Ditoo daemon runtime to ~/.ditoo (outside ~/Documents,
# which macOS TCC blocks launchd from reading). Re-run after changing code/art.
#
# Usage: sh tools/deploy.sh
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/.ditoo"

echo "Deploying runtime: $REPO -> $DEST"
mkdir -p "$DEST/pixels" "$DEST/hooks"

# Runtime python modules + art + hook
cp "$REPO/daemon.py"        "$DEST/"
cp "$REPO/transport.py"     "$DEST/"
cp "$REPO/divoom_proto.py"  "$DEST/"
cp "$REPO/pixels_loader.py" "$DEST/"
cp "$REPO/requirements.txt" "$DEST/"
cp "$REPO/pixels/"*.json    "$DEST/pixels/"
cp "$REPO/hooks/notify.py"  "$DEST/hooks/"

# Self-contained venv with the Bluetooth + image deps
if [ ! -x "$DEST/.venv/bin/python" ]; then
  echo "Creating venv at $DEST/.venv ..."
  /usr/bin/python3 -m venv "$DEST/.venv"
fi
echo "Installing dependencies ..."
"$DEST/.venv/bin/python" -m pip install --quiet --upgrade pip
"$DEST/.venv/bin/python" -m pip install --quiet -r "$DEST/requirements.txt"

echo "Done. Runtime ready at $DEST"
echo "Daemon:  $DEST/.venv/bin/python $DEST/daemon.py"
echo "Hook:    /usr/bin/python3 $DEST/hooks/notify.py <state>"
