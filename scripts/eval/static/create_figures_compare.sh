#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
FIGURES="$REPO_ROOT/src/util/staticFiguresCompare.py"

if [[ "$#" -lt 4 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	echo "Usage: $0 <oracle_aggregate_csv> <no_repair_aggregate_csv> <repair_aggregate_csv> <output_dir>"
	python3 "$FIGURES" --help
	exit 0
fi

echo "Oracle CSV: $1"
echo "No-repair CSV: $2"
echo "Repair CSV: $3"
echo "Output folder: $4"

cd "$REPO_ROOT"
mkdir -p "$4"
exec python3 "$FIGURES" "$@"
