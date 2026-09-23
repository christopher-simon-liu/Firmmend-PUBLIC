#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
FIGURES="$REPO_ROOT/src/util/staticAUC.py"

if [[ "$#" -lt 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	echo "Usage: $0 <output_dir> <repair_auc_compare_csv> [repair_auc_compare_csv ...] [--labels <label ...>]"
	python3 "$FIGURES" --help
	exit 0
fi

echo "Output folder: $1"
echo "AUC comparison CSVs: ${*:2}"

cd "$REPO_ROOT"
mkdir -p "$1"
exec python3 "$FIGURES" "$@"
