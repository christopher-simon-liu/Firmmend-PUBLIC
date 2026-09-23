#!/usr/bin/env bash
# run_coverage_calc_plus.sh — augment existing Fuzzware coverage results
# with coverage_ratio = corrupted_blocks / baseline_blocks,
# and coverage_retention = intersection(baseline_blocks, corrupted_blocks) / baseline_blocks.
#
# Usage: ./scripts/run_coverage_calc_plus.sh INPUT OUTPUT [options]
# This script expects run_coverage_calc.sh to have already written the
# *_fuzzware_blocks.txt artifacts in OUTPUT, including a corresponding
# severity-0.0 run for baseline comparison.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SUMMARY="$REPO_ROOT/src/measurement/dynamic/fuzzware_summary.py"

if [[ $# -lt 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	echo "Usage: $0 <input> <output>"
	echo
	echo "Adds coverage_ratio and coverage_retention fields to existing *_fuzzware.json results using"
	echo "the already-generated *_fuzzware_blocks.txt and a corresponding severity-0.0"
	echo "*_fuzzware_blocks.txt baseline artifact."
	exit 0
fi

INPUT_RUN_DIR="$1"
OUTPUT_ROOT="$2"

echo "Input run folder:  $INPUT_RUN_DIR"
echo "Output folder: $OUTPUT_ROOT"

if [[ ! -d "$INPUT_RUN_DIR" ]]; then
	echo "Skipping: Input run folder does not exist: $INPUT_RUN_DIR"
	exit 0
fi

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
BLOCKS_PATH="$OUTPUT_ROOT/$RUN_NAME/${BINARY_NAME}_fuzzware_blocks.txt"
SUMMARY_PATH="$OUTPUT_ROOT/$RUN_NAME/${BINARY_NAME}_fuzzware.json"

if [[ ! -f "$BLOCKS_PATH" ]]; then
	echo "Skipping: existing coverage blocks file not found: $BLOCKS_PATH"
	echo "Run ./scripts/run_coverage_calc.sh first to generate baseline coverage outputs."
	exit 0
fi

BASELINE_BLOCKS_FILE=""
if [[ "$BINARY_NAME" =~ ^(.+)-([0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\.bin$ ]]; then
	BASELINE_BINARY_NAME="${BASH_REMATCH[1]}-0.0.bin"
else
	echo "Skipping: Could not parse mode-severity suffix from binary name: $BINARY_NAME"
	exit 0
fi

if [[ "$BASELINE_BINARY_NAME" == "$BINARY_NAME" ]]; then
	BASELINE_BLOCKS_FILE="$BLOCKS_PATH"
else
	mapfile -t BASELINE_CANDIDATES < <(find "$OUTPUT_ROOT" -type f -name "${BASELINE_BINARY_NAME}_fuzzware_blocks.txt" | sort)
	if [[ "${#BASELINE_CANDIDATES[@]}" -eq 0 ]]; then
		echo "Skipping: Could not find corresponding severity-0.0 baseline blocks artifact for $BINARY_NAME"
		echo "Expected filename: ${BASELINE_BINARY_NAME}_fuzzware_blocks.txt under $OUTPUT_ROOT"
		exit 0
	fi
	BASELINE_BLOCKS_FILE="${BASELINE_CANDIDATES[0]}"
	if [[ "${#BASELINE_CANDIDATES[@]}" -gt 1 ]]; then
		echo "Note: Multiple severity-0.0 baseline artifacts found; using first sorted match:"
		echo "  $BASELINE_BLOCKS_FILE"
	fi
fi

cd "$REPO_ROOT"
mkdir -p "$OUTPUT_ROOT/$RUN_NAME"
python3 "$SUMMARY" "$BINARY_NAME" "$BLOCKS_PATH" "$SUMMARY_PATH" "$BASELINE_BLOCKS_FILE"

echo "Read blocks file:    $BLOCKS_PATH"
echo "Read baseline file:  $BASELINE_BLOCKS_FILE"
echo "Wrote summary file:  $SUMMARY_PATH"
