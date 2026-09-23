#!/usr/bin/env bash
# run_pixel_art.sh — wrapper for src/util/binary2mage.py
# Usage: ./scripts/run_pixel_art.sh INPUT OUTPUT [options]
# Options are passed through unchanged to binary2mage.py.
# Run with -h or --help to see all available options.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
CONVERTER="$REPO_ROOT/src/util/binary2mage.py"

if [[ $# -lt 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    echo "Usage: $0 <input> <output> [options]"
    python3 "$CONVERTER" --help
    exit 0
fi

echo "Input folder:  $1"
echo "Output folder: $2"

cd "$REPO_ROOT"
mkdir -p "$2"
exec python3 "$CONVERTER" "$@"

