#!/usr/bin/env bash
# run_provenance.sh — wrapper for src/util/provenance.py
# Usage: ./scripts/run_provenance.sh ORIGINAL_FOLDER MODIFIED_FOLDER OUTPUT_FOLDER
# Additional options are passed through unchanged to provenance.py.
# Run with -h or --help to see all available options.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
PROVENANCE="$REPO_ROOT/src/util/provenance.py"

if [[ $# -lt 3 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	echo "Usage: $0 <original_folder> <modified_folder> <output_folder> [options]"
	python3 "$PROVENANCE" --help
	exit 0
fi

echo "Original folder: $1"
echo "Modified folder: $2"
echo "Output folder:   $3"

cd "$REPO_ROOT"
mkdir -p "$3"
exec python3 "$PROVENANCE" "$@"

