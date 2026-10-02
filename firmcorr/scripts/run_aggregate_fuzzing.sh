#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
AGGREGATE="$REPO_ROOT/src/util/dynamicAggregate.py"

if [[ "$#" -lt 2  || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    echo "Usage: $0 <path/workspace/to/results> <path/workspace/to/output_dir>"
    python3 "$AGGREGATE" --help
    exit 0
fi


echo "Results folder: $1"
echo "Output folder: $2"

cd "$REPO_ROOT"
mkdir -p "$2"
exec python3 "$AGGREGATE" "$@"
