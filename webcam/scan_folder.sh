#!/usr/bin/env bash
# Scan a folder of JPG photos of a white-rectangle/black-frame document,
# correct perspective distortion, crop, resize to 367x483 and save as PNG.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "$SCRIPT_DIR/.venv/bin/python3" ]]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python3"
else
    PYTHON="python3"
fi

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <folder>" >&2
    exit 2
fi

FOLDER="$1"

if [[ ! -d "$FOLDER" ]]; then
    echo "Error: '$FOLDER' is not a directory" >&2
    exit 2
fi

processed=0
skipped_existing=0
skipped_failed=0

shopt -s nullglob nocaseglob
files=("$FOLDER"/*.jpg)
shopt -u nocaseglob

for jpg in "${files[@]}"; do
    png="${jpg%.*}.png"
    if [[ -f "$png" ]]; then
        echo "[SKIP] $(basename "$jpg"): $(basename "$png") already exists"
        skipped_existing=$((skipped_existing + 1))
        continue
    fi

    if "$PYTHON" "$SCRIPT_DIR/scan_card.py" "$jpg"; then
        processed=$((processed + 1))
    else
        skipped_failed=$((skipped_failed + 1))
    fi
done

echo
echo "Done: $processed processed, $skipped_existing skipped (existing), $skipped_failed skipped (failed)"
