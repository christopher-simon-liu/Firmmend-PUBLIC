#!/usr/bin/env bash
# run_manifest.sh — wrapper for src/util/manifest.py
# Usage: ./scripts/run_manifest.sh MENDED_BINARY CORRUPTED_BINARY ORIGINAL_BINARY OUTPUT_FOLDER [options]
# Additional options are passed through unchanged to manifest.py.
# Run with -h or --help to see all available options.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
MANIFEST="$REPO_ROOT/src/util/manifest.py"

if [[ $# -lt 4 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	echo "Usage: $0 <mended_binary> <corrupted_binary> <original_binary> <output_folder> [options]"
	python3 "$MANIFEST" --help
	exit 0
fi

echo "Mended binary:    $1"
echo "Corrupted binary: $2"
echo "Original binary:  $3"
echo "Output folder:    $4"

cd "$REPO_ROOT"
mkdir -p "$4"
exec python3 "$MANIFEST" "$@"
