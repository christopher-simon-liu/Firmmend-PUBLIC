#!/usr/bin/env bash
# run_corrupter_all.sh — batch wrapper for experiment_matrix.csv
# Usage: ./scripts/run_corrupter_all.sh

set -euo pipefail

if [ "$#" -ne 0 ]; then
	echo "Usage: $0"
	exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MATRIX="$REPO_ROOT/experiment_matrix.csv"
WRAPPER="$SCRIPT_DIR/run_corrupter.sh"

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

if [ ! -f "$MATRIX" ]; then
	echo "Error: matrix file not found: experiment_matrix.csv" >&2
	exit 1
fi

if [ ! -x "$WRAPPER" ]; then
	echo "Error: corrupter wrapper not found or not executable: scripts/run_corrupter.sh" >&2
	exit 1
fi

trim() {
	local value="$1"
	value="${value#${value%%[![:space:]]*}}"
	value="${value%${value##*[![:space:]]}}"
	printf '%s' "$value"
}

progress_bar() {
	local current="$1"
	local total="$2"
	local width=30
	local filled=0
	local percent=0

	if [ "$total" -gt 0 ]; then
		filled=$((current * width / total))
		percent=$((current * 100 / total))
	fi

	printf '['
	printf '%*s' "$filled" '' | tr ' ' '#'
	printf '%*s' "$((width - filled))" '' | tr ' ' '-'
	printf '] %3d%% (%d/%d)' "$percent" "$current" "$total"
}

echo "Matrix: experiment_matrix.csv"
echo "Wrapper: scripts/run_corrupter.sh"

total_runs=$(tail -n +2 "$MATRIX" | sed '/^\s*$/d' | wc -l | tr -d ' ')
current_run=0

tail -n +2 "$MATRIX" | while IFS=, read -r input_binary mode severity random_seed data_start data_end output_folder; do
	input_binary="$(trim "$input_binary")"
	mode="$(trim "$mode")"
	severity="$(trim "$severity")"
	random_seed="$(trim "$random_seed")"
	data_start="$(trim "$data_start")"
	data_end="$(trim "$data_end")"
	output_folder="$(trim "$output_folder")"

	if [ -z "$input_binary" ]; then
		continue
	fi

	current_run=$((current_run + 1))

	printf '\r'
	progress_bar "$current_run" "$total_runs"
	printf ' Running: %s | %s | severity %s | seed %s\n' "$input_binary" "$mode" "$severity" "$random_seed"
	if [ -z "$random_seed" ]; then
		echo "Error: missing random_seed for $input_binary / $mode / $severity" >&2
		exit 1
	fi

	input_binary_rel="$(to_repo_relative "$input_binary")"
	output_folder_rel="$(to_repo_relative "$output_folder")"
	input_binary_abs="$REPO_ROOT/$input_binary_rel"
	output_folder_abs="$REPO_ROOT/$output_folder_rel"
	dataset_dir_abs="$(dirname "$input_binary_abs")"

	if [ ! -f "$input_binary_abs" ]; then
		echo "Error: input binary not found: $input_binary_rel" >&2
		exit 1
	fi

	if [ ! -d "$dataset_dir_abs" ]; then
		echo "Error: dataset directory not found for input: $dataset_dir_abs" >&2
		exit 1
	fi

	mkdir -p "$output_folder_abs"
	if [ "$dataset_dir_abs" != "$output_folder_abs" ]; then
		cp -a "$dataset_dir_abs/." "$output_folder_abs/"
	fi

	cmd=("$WRAPPER" "$mode" "$severity" "$data_start" "$data_end" "$input_binary" "$output_folder" "$random_seed")
	"${cmd[@]}"
done

printf '\r'
progress_bar "$total_runs" "$total_runs"
printf ' Done\n'

