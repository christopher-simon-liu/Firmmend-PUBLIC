#!/usr/bin/env bash
# run_pixel_art_all.sh — recursively run run_pixel_art.sh on subfolders.
# Usage: ./scripts/run_pixel_art_all.sh [INPUT_ROOT] [OUTPUT_ROOT] [options]
# Extra options are passed through unchanged to run_pixel_art.sh.
#
# For each folder that contains .bin files, output is written to
# OUTPUT_ROOT/<path relative to INPUT_ROOT> or <that_folder>/figures.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
RUN_ONE="$SCRIPT_DIR/run_pixel_art.sh"

usage() {
	echo "Usage: $0 [INPUT_ROOT] [OUTPUT_ROOT] [options]"
	echo ""
	echo "Recursively finds folders under INPUT_ROOT and runs run_pixel_art.sh"
	echo "for each folder that contains .bin files."
	echo "INPUT_ROOT defaults to repairs (or firmcorr/dataset/corruption if repairs does not exist)."
	echo "OUTPUT_ROOT defaults to ./figures inside each input folder."
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	usage
	exit 0
fi

resolve_path() {
	if [[ "$1" = /* ]]; then
		printf '%s' "$1"
	else
		printf '%s' "$REPO_ROOT/$1"
	fi
}

INPUT_ROOT_RAW=""
OUTPUT_ROOT_RAW=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
	case "$1" in
		-*)
			EXTRA_ARGS+=("$1")
			shift
			;;
		*)
			if [[ -z "$INPUT_ROOT_RAW" ]]; then
				INPUT_ROOT_RAW="$1"
			elif [[ -z "$OUTPUT_ROOT_RAW" ]]; then
				OUTPUT_ROOT_RAW="$1"
			else
				EXTRA_ARGS+=("$1")
			fi
			shift
			;;
	esac
done

if [[ -z "$INPUT_ROOT_RAW" ]]; then
	if [[ -d "$REPO_ROOT/repairs" ]]; then
		INPUT_ROOT_RAW="repairs"
	else
		INPUT_ROOT_RAW="firmcorr/dataset/corruption"
	fi
fi

INPUT_ROOT="$(resolve_path "$INPUT_ROOT_RAW")"
OUTPUT_ROOT=""
if [[ -n "$OUTPUT_ROOT_RAW" ]]; then
	OUTPUT_ROOT="$(resolve_path "$OUTPUT_ROOT_RAW")"
fi

if [[ ! -d "$INPUT_ROOT" ]]; then
	echo "Error: input root does not exist or is not a directory: $INPUT_ROOT" >&2
	exit 1
fi

if [[ ! -x "$RUN_ONE" ]]; then
	echo "Error: missing executable wrapper: $RUN_ONE" >&2
	exit 1
fi

INPUT_ROOT_ABS="$(cd "$INPUT_ROOT" && pwd)"

count=0
while IFS= read -r -d '' dir; do
	if compgen -G "$dir"/*.bin > /dev/null; then
		if [[ -n "$OUTPUT_ROOT" ]]; then
			rel_dir="${dir#"$INPUT_ROOT_ABS"}"
			rel_dir="${rel_dir#/}"
			if [[ -n "$rel_dir" ]]; then
				out_dir="$OUTPUT_ROOT/$rel_dir"
			else
				out_dir="$OUTPUT_ROOT"
			fi
		else
			out_dir="$dir/figures"
		fi
		echo "Processing: $dir"
		echo "Output:     $out_dir"
		mkdir -p "$out_dir"
		"$RUN_ONE" "$dir" "$out_dir" "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
		count=$((count + 1))
	fi
done < <(find "$INPUT_ROOT_ABS" -type d \( -name figures -prune -o -print0 \) | sort -z)

echo "Done. Processed $count folders with .bin files."

