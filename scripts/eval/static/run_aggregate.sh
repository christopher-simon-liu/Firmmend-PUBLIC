#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
AGGREGATE="$REPO_ROOT/src/util/staticAggregate.py"

usage() {
    echo "Usage: $0 [path/workspace/to/results] [path/workspace/to/output_dir]"
    echo "results defaults to results."
    echo "output_dir defaults to results."
    python3 "$AGGREGATE" --help
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

RESULTS_ROOT_RAW="${1:-results}"
OUTPUT_DIR_RAW="${2:-results}"
if [[ $# -ge 2 ]]; then
    shift 2
elif [[ $# -eq 1 ]]; then
    shift 1
fi

RESULTS_ROOT="$RESULTS_ROOT_RAW"
OUTPUT_DIR="$OUTPUT_DIR_RAW"

echo "Results root: $RESULTS_ROOT"
echo "Output folder: $OUTPUT_DIR"

cd "$REPO_ROOT"
mkdir -p "$OUTPUT_DIR"

if [[ ! -d "$RESULTS_ROOT" ]]; then
    echo "Error: results root does not exist or is not a directory: $RESULTS_ROOT" >&2
    exit 1
fi

failed=0
for method_dir in "$RESULTS_ROOT"/*/; do
    [[ -d "$method_dir" ]] || continue
    method_name="$(basename "$method_dir")"
    echo "=== $method_name ==="
    if ! python3 "$AGGREGATE" "$method_dir" "$OUTPUT_DIR/$method_name" "$@"; then
        echo "Error: aggregate failed for $method_name" >&2
        failed=1
        continue
    fi
done

exit "$failed"