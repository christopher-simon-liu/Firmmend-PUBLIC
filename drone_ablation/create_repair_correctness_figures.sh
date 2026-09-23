#!/usr/bin/env bash
# Aggregate manifest repair correctness and create comparison figures.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
FIGURES="$REPO_ROOT/src/util/repairCorrectness.py"

usage() {
	echo "Usage: $0 [MANIFEST_ROOT] [OUTPUT_FOLDER]"
	echo "MANIFEST_ROOT defaults to JUST_DRONES_ABLATION/repairs."
	echo "OUTPUT_FOLDER defaults to JUST_DRONES_ABLATION/figures/repair_correctness."
	python3 "$FIGURES" --help
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	usage
	exit 0
fi

MANIFEST_ROOT="${1:-JUST_DRONES_ABLATION/repairs}"
OUTPUT_FOLDER="${2:-JUST_DRONES_ABLATION/figures/repair_correctness}"

echo "Manifest root: $MANIFEST_ROOT"
echo "Output folder: $OUTPUT_FOLDER"

cd "$REPO_ROOT"
exec python3 "$FIGURES" "$MANIFEST_ROOT" "$OUTPUT_FOLDER"
