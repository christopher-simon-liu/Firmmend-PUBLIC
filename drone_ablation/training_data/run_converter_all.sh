#!/bin/bash

set -euo pipefail

if [ "$#" -gt 2 ]; then
	echo "Usage: $0 [input_subdir] [output_subdir]"
	echo "Defaults: training_data/original training_data/extraction"
	exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DENOISING_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

to_denoising_relative() {
	local input_path="$1"
	local abs_path

	case "$input_path" in
		/*)
			abs_path="$(realpath -m "$input_path")"
			;;
		*)
			abs_path="$(realpath -m "$DENOISING_ROOT/$input_path")"
			;;
	esac

	case "$abs_path" in
		"$DENOISING_ROOT"/*)
			printf '%s\n' "${abs_path#$DENOISING_ROOT/}"
			;;
		*)
			echo "Error: path must be inside denoising_autoencoder: $input_path" >&2
			exit 1
			;;
	esac
}

INPUT_ROOT_REL="$(to_denoising_relative "${1:-training_data/original}")"
INPUT_ROOT_ABS="$DENOISING_ROOT/$INPUT_ROOT_REL"
OUTPUT_ROOT_REL="$(to_denoising_relative "${2:-training_data/extraction}")"
OUTPUT_ROOT_ABS="$DENOISING_ROOT/$OUTPUT_ROOT_REL"

METADATA_REL="training_data/Dataset_Metadata.csv"
METADATA_ABS="$DENOISING_ROOT/$METADATA_REL"

if [ ! -d "$INPUT_ROOT_ABS" ]; then
	echo "Error: input directory not found: $INPUT_ROOT_REL" >&2
	exit 1
fi

if [ ! -f "$METADATA_ABS" ]; then
	echo "Error: metadata file not found: $METADATA_REL" >&2
	exit 1
fi

WRAPPER="$SCRIPT_DIR/run_converter.sh"
if [ ! -x "$WRAPPER" ]; then
	echo "Error: converter wrapper not found or not executable (expected run_converter.sh)" >&2
	exit 1
fi

mkdir -p "$OUTPUT_ROOT_ABS"

echo "Input root: $INPUT_ROOT_REL"
echo "Metadata: $METADATA_REL"
echo "Output root: $OUTPUT_ROOT_REL"
echo "Wrapper: $(basename "$WRAPPER")"

tail -n +2 "$METADATA_ABS" | while IFS=, read -r firmware _architecture mcu _os _loc _elf_size _bin_size _source; do
	firmware="$(printf '%s' "$firmware" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
	mcu="$(printf '%s' "$mcu" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
	[ -z "$firmware" ] && continue

	dataset_dir_rel="$INPUT_ROOT_REL/$firmware"
	dataset_dir_abs="$DENOISING_ROOT/$dataset_dir_rel"

	if [ ! -d "$dataset_dir_abs" ]; then
		IFS= read -r dataset_dir_abs < <(
			find "$INPUT_ROOT_ABS" -mindepth 2 -maxdepth 2 -type d -name "$firmware" \
				-print -quit
		)
		if [ -n "$dataset_dir_abs" ]; then
			dataset_dir_rel="${dataset_dir_abs#$DENOISING_ROOT/}"
		else
			echo "Skipping $firmware: dataset directory missing below $INPUT_ROOT_REL"
			continue
		fi
	fi

	input_rel=""
	for ext in elf hex apj bin; do
		candidate_rel="$dataset_dir_rel/$firmware.$ext"
		if [ -f "$DENOISING_ROOT/$candidate_rel" ]; then
			input_rel="$candidate_rel"
			break
		fi
	done

	if [ -z "$input_rel" ]; then
		fallback_input_abs=""
		IFS= read -r fallback_input_abs < <(
			find "$dataset_dir_abs" -maxdepth 1 -type f \( -iname '*.hex' -o -iname '*.bin' \) \
				-print | sort | head -n 1
		)
		if [ -n "$fallback_input_abs" ]; then
			input_rel="${fallback_input_abs#$DENOISING_ROOT/}"
		fi
	fi

	if [ -z "$input_rel" ]; then
		echo "Skipping $firmware: no matching input file found (.elf/.hex/.apj/.bin, or fallback .hex/.bin)"
		continue
	fi

	dataset_subdir_rel="${dataset_dir_rel#$INPUT_ROOT_REL/}"
	category_rel="${dataset_subdir_rel%%/*}"
	if [ "$category_rel" = "$dataset_subdir_rel" ]; then
		output_dir_rel="$OUTPUT_ROOT_REL/$firmware"
	else
		output_dir_rel="$OUTPUT_ROOT_REL/$category_rel/$firmware"
	fi
	output_rel="$output_dir_rel/$firmware.bin"
	output_dir_abs="$DENOISING_ROOT/$output_dir_rel"

	mkdir -p "$output_dir_abs"
	if [ "$dataset_dir_abs" != "$output_dir_abs" ]; then
		while IFS= read -r -d '' source_file_abs; do
			source_file_rel="${source_file_abs#$dataset_dir_abs/}"
			mkdir -p "$output_dir_abs/$(dirname "$source_file_rel")"
			cp -a "$source_file_abs" "$output_dir_abs/$source_file_rel"
		done < <(find "$dataset_dir_abs" -type f ! -iname '*.bin' -print0)
	fi

	echo "Converting $firmware"
	echo "  Input: $input_rel"
	echo "  Output: $output_rel"
	echo "  Copied non-bin files: $dataset_dir_rel -> $output_dir_rel"
	echo "  MCU: $mcu"

	cmd=("$WRAPPER" "$input_rel" "$output_rel")
	if [ -n "$mcu" ]; then
		cmd+=(--chip-part "$mcu")
	fi

	"${cmd[@]}"
done

