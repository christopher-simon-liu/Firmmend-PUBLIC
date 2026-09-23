#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
FIGURES="$REPO_ROOT/src/util/figures_fuzzing.py"

if [[ "$#" -lt 2  || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	echo "Usage: $0 <path/to/dynamic_aggregate_csv> <path/to/output_dir>"
	python3 "$FIGURES" --help
	exit 0
fi


echo "Aggregate csv: $1"
echo "Output folder: $2"

cd "$REPO_ROOT"
mkdir -p "$2"
exec python3 "$FIGURES" "$@"
