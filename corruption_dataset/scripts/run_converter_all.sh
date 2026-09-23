#!/bin/bash

set -euo pipefail

if [ "$#" -ne 2 ]; then
	echo "Usage: $0 <path/workspace/to/input_dir> <path/workspace/to/output_dir>"
	exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

to_repo_relative() {
	local input_path="$1"

	case "$input_path" in
		/*)
			case "$input_path" in
				"$REPO_ROOT"/*)
					printf '%s\n' "${input_path#$REPO_ROOT/}"
					;;
				*)
					echo "Error: path must be inside the repository root: $input_path" >&2
					exit 1
					;;
			esac
			;;
		*)
			printf '%s\n' "$input_path"
			;;
	esac
}

INPUT_ROOT_REL="$(to_repo_relative "$1")"
INPUT_ROOT_ABS="$REPO_ROOT/$INPUT_ROOT_REL"
OUTPUT_ROOT_REL="$(to_repo_relative "$2")"
OUTPUT_ROOT_ABS="$REPO_ROOT/$OUTPUT_ROOT_REL"

METADATA_REL="$INPUT_ROOT_REL/Dataset_Metadata.csv"
METADATA_ABS="$REPO_ROOT/$METADATA_REL"

if [ ! -d "$INPUT_ROOT_ABS" ]; then
	echo "Error: input directory not found: $INPUT_ROOT_REL" >&2
	exit 1
fi

if [ ! -f "$METADATA_ABS" ]; then
	echo "Error: metadata file not found: $METADATA_REL" >&2
	exit 1
fi

WRAPPER="$SCRIPT_DIR/run_conveter.sh"
if [ ! -x "$WRAPPER" ]; then
	WRAPPER="$SCRIPT_DIR/run_converter.sh"
fi
if [ ! -x "$WRAPPER" ]; then
	echo "Error: converter wrapper not found or not executable (expected run_conveter.sh or run_converter.sh)" >&2
	exit 1
fi

mkdir -p "$OUTPUT_ROOT_ABS"

echo "Input root: $INPUT_ROOT_REL"
echo "Metadata: $METADATA_REL"
echo "Output root: $OUTPUT_ROOT_REL"
echo "Wrapper: $(basename "$WRAPPER")"

tail -n +2 "$METADATA_ABS" | while IFS=, read -r firmware _architecture mcu _os _loc _elf_size _bin_size _source; do
	[ -z "$firmware" ] && continue

	dataset_dir_rel="$INPUT_ROOT_REL/$firmware"
	dataset_dir_abs="$REPO_ROOT/$dataset_dir_rel"

	if [ ! -d "$dataset_dir_abs" ]; then
		echo "Skipping $firmware: dataset directory missing: $dataset_dir_rel"
		continue
	fi

	input_rel=""
	for ext in elf hex apj bin; do
		candidate_rel="$dataset_dir_rel/$firmware.$ext"
		if [ -f "$REPO_ROOT/$candidate_rel" ]; then
			input_rel="$candidate_rel"
			break
		fi
	done

	if [ -z "$input_rel" ]; then
		echo "Skipping $firmware: no matching input file found (.elf/.hex/.apj/.bin)"
		continue
	fi

	output_rel="$OUTPUT_ROOT_REL/$firmware/$firmware.bin"
	output_dir_rel="$OUTPUT_ROOT_REL/$firmware"
	output_dir_abs="$REPO_ROOT/$output_dir_rel"

	mkdir -p "$output_dir_abs"
	if [ "$dataset_dir_abs" != "$output_dir_abs" ]; then
		cp -a "$dataset_dir_abs/." "$output_dir_abs/"
	fi

	echo "Converting $firmware"
	echo "  Input: $input_rel"
	echo "  Output: $output_rel"
	echo "  Copied: $dataset_dir_rel -> $output_dir_rel"
	echo "  MCU: $mcu"

	cmd=("$WRAPPER" "$input_rel" "$output_rel")
	if [ -n "$mcu" ]; then
		cmd+=(--chip-part "$mcu")
	fi

	"${cmd[@]}"
done

