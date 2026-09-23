#!/usr/bin/env bash

set -euo pipefail

log_info() {
	echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"
}

log_warn() {
	echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN] $*"
}

log_error() {
	echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2
}

print_progress() {
	local current="$1"
	local total="$2"
	local width=40
	local filled=0
	local percent=0

	if (( total > 0 )); then
		filled=$(( current * width / total ))
		percent=$(( current * 100 / total ))
	fi

	local empty=$(( width - filled ))
	local bar
	bar="$(printf '%*s' "$filled" '' | tr ' ' '#')$(printf '%*s' "$empty" '' | tr ' ' '-')"

	printf '\rProgress: [%s] %3d%% (%d/%d)' "$bar" "$percent" "$current" "$total"
	if (( current == total )); then
		printf '\n'
	fi
}

usage() {
	echo "Usage: $0 <input_folder> <output_folder>"
	exit 1
}

if [[ $# -ne 2 ]]; then
	usage
fi

INPUT_DIR="$1"
OUTPUT_DIR="$2"

if [[ ! -d "$INPUT_DIR" ]]; then
	log_error "Input folder does not exist: $INPUT_DIR"
	exit 1
fi

if ! command -v zip >/dev/null 2>&1; then
	log_error "'zip' command not found. Please install zip and try again."
	exit 1
fi

mkdir -p "$OUTPUT_DIR"

mapfile -t SUBDIRS < <(find "$INPUT_DIR" -mindepth 1 -maxdepth 1 -type d | sort)

if (( ${#SUBDIRS[@]} == 0 )); then
	log_warn "No subfolders found in input folder: $INPUT_DIR"
fi

total_steps=$(( ${#SUBDIRS[@]} + 1 ))
completed_steps=0

log_info "Starting archive creation"
log_info "Input folder: $INPUT_DIR"
log_info "Output folder: $OUTPUT_DIR"
print_progress "$completed_steps" "$total_steps"

for subdir in "${SUBDIRS[@]}"; do
	if [[ -d "$subdir" ]]; then
		name="$(basename "$subdir")"
		zip_path="$OUTPUT_DIR/${name}.zip"

		if [[ -f "$zip_path" ]]; then
			log_info "Skipping existing subfolder archive: $zip_path"
		else
			# -r recursively includes files and folders.
			zip -r "$zip_path" "$subdir"
			log_info "Created subfolder archive: $zip_path"
		fi

		completed_steps=$(( completed_steps + 1 ))
		print_progress "$completed_steps" "$total_steps"
	fi
done

output_base="$(basename "$OUTPUT_DIR")"
parent_dir="$(dirname "$OUTPUT_DIR")"
final_zip="$parent_dir/${output_base}.zip"

# Create a compressed archive of the output folder itself.
if [[ -f "$final_zip" ]]; then
	log_info "Skipping existing final archive: $final_zip"
else
	(
		cd "$parent_dir"
		zip -r "${output_base}.zip" "$output_base"
	)
	log_info "Created final archive: $final_zip"
fi

completed_steps=$(( completed_steps + 1 ))
print_progress "$completed_steps" "$total_steps"

log_info "All archive operations completed successfully"
