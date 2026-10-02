#!/usr/bin/env bash
# run_coverage_calc_all.sh — recursively discover run_# folders and
# invoke run_coverage_calc.sh for each.
#
# Usage:
#   ./scripts/run_coverage_calc_all.sh <input_root> <output_root> [options]
#
# Any additional options are forwarded unchanged to run_coverage_calc.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ONE="$SCRIPT_DIR/run_coverage_calc.sh"

if [[ $# -lt 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	echo "Usage: $0 <input_root> <output_root> [options]"
	echo
	echo "Recursively finds run_# folders and runs coverage extraction for each."
	echo "Options are forwarded to run_coverage_calc.sh."
	exit 0
fi

INPUT_ROOT="$1"
OUTPUT_ROOT="$2"
shift 2

if [[ ! -d "$INPUT_ROOT" ]]; then
	echo "Error: Input root does not exist: $INPUT_ROOT"
	exit 1
fi

mkdir -p "$OUTPUT_ROOT"

RUN_DIRS=()
for candidate in "$INPUT_ROOT"/run_*; do
	if [[ -d "$candidate" ]]; then
		base_name="$(basename "$candidate")"
		if [[ "$base_name" =~ ^run_[0-9]+$ ]]; then
			RUN_DIRS+=("$candidate")
		fi
	fi
done

IFS=$'\n' RUN_DIRS=($(printf "%s\n" "${RUN_DIRS[@]}" | sort))
TOTAL_RUNS="${#RUN_DIRS[@]}"

if [[ "$TOTAL_RUNS" -eq 0 ]]; then
	echo "No run_# folders found under: $INPUT_ROOT"
	exit 0
fi

echo "Input root:  $INPUT_ROOT"
echo "Output root: $OUTPUT_ROOT"
echo "Found $TOTAL_RUNS run folders"

CURRENT=0
for RUN_DIR in "${RUN_DIRS[@]}"; do
	CURRENT=$((CURRENT + 1))
	echo "[$CURRENT/$TOTAL_RUNS] Processing: $RUN_DIR"
	RUN_NAME="$(basename "$RUN_DIR")"
	RUN_OUTPUT_DIR="$OUTPUT_ROOT/$RUN_NAME"

	if compgen -G "$RUN_OUTPUT_DIR/*_fuzzware_blocks.txt" > /dev/null \
		|| compgen -G "$RUN_OUTPUT_DIR/*_fuzzware.json" > /dev/null; then
		echo "[$CURRENT/$TOTAL_RUNS] Skipping: output already exists in $RUN_OUTPUT_DIR"
		continue
	fi

	"$RUN_ONE" "$RUN_DIR" "$OUTPUT_ROOT" "$@"
done

echo "Completed coverage extraction for $TOTAL_RUNS run folders."
