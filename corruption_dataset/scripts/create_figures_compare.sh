#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
FIGURES="$REPO_ROOT/src/util/figures_compare.py"

if [[ "$#" -lt 3  || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	echo "Usage: $0 <path/to/static_results_csv> <path/to/dynamic_results_csv> <path/to/output_dir>"
	python3 "$FIGURES" --help
	exit 0
fi


echo "Static csv: $1"
echo "Dynamic csv: $2"
echo "Output folder: $3"

cd "$REPO_ROOT"
mkdir -p "$3"
exec python3 "$FIGURES" "$@"
