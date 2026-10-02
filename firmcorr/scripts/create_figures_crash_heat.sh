#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
FIGURES="$REPO_ROOT/src/util/figures_coverage_heat.py"

if [[ "$#" -lt 2  || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	echo "Usage: $0 <path/to/dynamic_results_csv> <path/to/output_dir>"
	echo "Runs crash-ratio heatmap generation (metric=crash_ratio)."
	python3 "$FIGURES" --help
	exit 0
fi


echo "Dynamic csv: $1"
echo "Output folder: $2"

cd "$REPO_ROOT"
mkdir -p "$2"
exec python3 "$FIGURES" "$1" "$2" --metric crash_ratio "${@:3}"
