#!/usr/bin/env bash
# run_diff.sh — wrapper for src/util/diff.py
# Usage: ./scripts/run_diff.sh CORRUPTED_BINARY MENDED_BINARY OUTPUT_FOLDER [options]
# Additional options are passed through unchanged to diff.py.
# Run with -h or --help to see all available options.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
DIFF="$REPO_ROOT/src/util/diff.py"

if [[ $# -lt 3 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	echo "Usage: $0 <corrupted_binary> <mended_binary> <output_folder> [options]"
	python3 "$DIFF" --help
	exit 0
fi

echo "Corrupted binary: $1"
echo "Mended binary:    $2"
echo "Output folder:    $3"

cd "$REPO_ROOT"
mkdir -p "$3"
exec python3 "$DIFF" "$@"
