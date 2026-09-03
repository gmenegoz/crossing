#!/usr/bin/env bash
# Scan a folder of JPG photos of a white-rectangle/black-frame document,
# correct perspective distortion, crop, resize and save as PNG.
#
# FOLDER, INDEX and DESTINATION are read from config.txt (next to this
# script). An optional command-line argument overrides FOLDER; INDEX and
# DESTINATION always come from config.txt regardless.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "$SCRIPT_DIR/.venv/bin/python3" ]]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python3"
else
    PYTHON="python3"
fi

if [[ $# -gt 1 ]]; then
    echo "Usage: $0 [folder]" >&2
    exit 2
fi

exec "$PYTHON" "$SCRIPT_DIR/scan_card.py" --config "$SCRIPT_DIR/config.txt" "$@"
