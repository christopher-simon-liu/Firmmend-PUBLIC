#!/usr/bin/env bash
# run_coverage_calc.sh — wrapper for src/util/calcFuzzCoverage.py
# Usage: ./scripts/run_coverage_calc.sh INPUT OUTPUT [options]
# Options are passed through unchanged to calcFuzzCoverage.py.
# Run with -h or --help to see all available options.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
CALC="$REPO_ROOT/src/util/calcFuzzCoverage.py"
SUMMARY="$REPO_ROOT/src/measurement/dynamic/fuzzware_summary.py"

if [[ $# -lt 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    echo "Usage: $0 <input> <output> [options]"
    python3 "$CALC" --help
    exit 0
fi

echo "Input run folder:  $1"
echo "Output folder: $2"

# check that input folder exists
if [[ ! -d "$1" ]]; then
    echo "Skipping: Input run folder does not exist: $1"
    exit 0
fi
# check that input/workdir/fuzzware-project exists
if [[ ! -d "$1/workdir/fuzzware-project" ]]; then
    echo "Skipping: fuzzware-project not found in input run folder: $1/workdir/fuzzware-project"
    exit 0
fi
RUN_NAME="$(basename "$1")"
INPUT_FIRMWARE=""
while IFS= read -r bin_path; do
    bin_name="$(basename "$bin_path")"
    if [[ "$bin_name" == *-*\.bin ]]; then
        INPUT_FIRMWARE="$bin_path"
        break
    fi
done < <(find "$1/workdir" -maxdepth 1 -type f -name "*.bin" | sort)

if [[ -z "$INPUT_FIRMWARE" ]]; then
    echo "Skipping: Could not find corrupted firmware .bin with mode-severity suffix in $1/workdir"
    exit 0
fi

BINARY_NAME="$(basename "$INPUT_FIRMWARE")"
BLOCKS_PATH="$2/$RUN_NAME/${BINARY_NAME}_fuzzware_blocks.txt"
SUMMARY_PATH="$2/$RUN_NAME/${BINARY_NAME}_fuzzware.json"

cd "$REPO_ROOT"
mkdir -p "$2/$RUN_NAME"
python3 "$CALC" "$1/workdir/fuzzware-project" --all-main-dirs -o "$BLOCKS_PATH"
python3 "$SUMMARY" "$BINARY_NAME" "$BLOCKS_PATH" "$SUMMARY_PATH"

echo "Wrote blocks file:   $BLOCKS_PATH"
echo "Wrote summary file:  $SUMMARY_PATH"

