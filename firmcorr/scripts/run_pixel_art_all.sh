#!/usr/bin/env bash
# run_pixel_art_all.sh — recursively run run_pixel_art.sh on subfolders.
# Usage: ./scripts/run_pixel_art_all.sh INPUT_ROOT [options]
# Extra options are passed through unchanged to run_pixel_art.sh.
#
# For each folder that contains .bin files, output is written to
# <that_folder>/figures.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
RUN_ONE="$SCRIPT_DIR/run_pixel_art.sh"

if [[ $# -lt 1 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	echo "Usage: $0 <input_root> [options]"
	echo ""
	echo "Recursively finds folders under <input_root> and runs run_pixel_art.sh"
	echo "for each folder that contains .bin files, writing output to ./figures"
	echo "inside that same folder."
	exit 0
fi

INPUT_ROOT_RAW="$1"
shift
EXTRA_ARGS=("$@")

# Resolve relative paths against repo root so invocation works from any cwd.
if [[ "$INPUT_ROOT_RAW" = /* ]]; then
	INPUT_ROOT="$INPUT_ROOT_RAW"
else
	INPUT_ROOT="$REPO_ROOT/$INPUT_ROOT_RAW"
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
		out_dir="$dir/figures"
		echo "Processing: $dir"
		echo "Output:     $out_dir"
		"$RUN_ONE" "$dir" "$out_dir" "${EXTRA_ARGS[@]}"
		count=$((count + 1))
	fi
done < <(find "$INPUT_ROOT_ABS" -type d \( -name figures -prune -o -print0 \) | sort -z)

echo "Done. Processed $count folders with .bin files."

