#!/usr/bin/env bash
# run_crash_calc.sh — wrapper for src/util/calcFuzzCrashes.py
# Usage: ./scripts/run_crash_calc.sh INPUT OUTPUT [options]
# Options are passed through unchanged to calcFuzzCrashes.py.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
CALC="$REPO_ROOT/src/util/calcFuzzCrashes.py"

if [[ $# -lt 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	echo "Usage: $0 <input> <output> [options]"
	python3 "$CALC" --help
	exit 0
fi

INPUT_RUN_DIR="$1"
OUTPUT_ROOT="$2"
shift 2

echo "Input run folder:  $INPUT_RUN_DIR"
echo "Output folder: $OUTPUT_ROOT"

# check that input folder exists
if [[ ! -d "$INPUT_RUN_DIR" ]]; then
	echo "Skipping: Input run folder does not exist: $INPUT_RUN_DIR"
	exit 0
fi

# check that input/workdir/fuzzware-project exists
if [[ ! -d "$INPUT_RUN_DIR/workdir/fuzzware-project" ]]; then
	echo "Skipping: fuzzware-project not found in input run folder: $INPUT_RUN_DIR/workdir/fuzzware-project"
	exit 0
fi

RUN_NAME="$(basename "$INPUT_RUN_DIR")"
INPUT_FIRMWARE=""
while IFS= read -r bin_path; do
	bin_name="$(basename "$bin_path")"
	if [[ "$bin_name" == *-*\.bin ]]; then
		INPUT_FIRMWARE="$bin_path"
		break
	fi
done < <(find "$INPUT_RUN_DIR/workdir" -maxdepth 1 -type f -name "*.bin" | sort)

if [[ -z "$INPUT_FIRMWARE" ]]; then
	echo "Skipping: Could not find corrupted firmware .bin with mode-severity suffix in $INPUT_RUN_DIR/workdir"
	exit 0
fi

BINARY_NAME="$(basename "$INPUT_FIRMWARE")"
SUMMARY_PATH="$OUTPUT_ROOT/$RUN_NAME/${BINARY_NAME}_fuzzware_crashes.json"

cd "$REPO_ROOT"
mkdir -p "$OUTPUT_ROOT/$RUN_NAME"
python3 "$CALC" "$INPUT_RUN_DIR/workdir/fuzzware-project" --all-main-dirs -o "$SUMMARY_PATH" "$@"

echo "Wrote crash summary:  $SUMMARY_PATH"
