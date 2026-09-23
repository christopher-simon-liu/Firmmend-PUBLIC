#!/usr/bin/env bash
# run_converter.sh - wrapper for the local training_data/converter.py
# Usage: ./training_data/run_converter.sh INPUT OUTPUT [options]
# Options are passed through unchanged to converter.py.
# Run with -h or --help to see all available options.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DENOISING_ROOT="$(dirname "$SCRIPT_DIR")"
CONVERTER="$SCRIPT_DIR/converter.py"

if [[ $# -lt 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    echo "Usage: $0 <input> <output> [options]"
    python3 "$CONVERTER" --help
    exit 0
fi

echo "Input file:  $1"
echo "Output file: $2"

cd "$DENOISING_ROOT"
exec python3 "$CONVERTER" "$@"

