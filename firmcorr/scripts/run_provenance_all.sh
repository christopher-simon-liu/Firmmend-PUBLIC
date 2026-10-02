#!/usr/bin/env bash
# run_provenance_all.sh — recursively run run_provenance.sh on corruption folders.
# Usage: ./scripts/run_provenance_all.sh ORIGINAL_ROOT MODIFIED_ROOT [options]
# Extra options are passed through unchanged to run_provenance.sh.
#
# For each modified .bin under MODIFIED_ROOT, this script finds the
# corresponding original binary by name and writes output to
# <modified-folder>/figures.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
RUN_ONE="$SCRIPT_DIR/run_provenance.sh"

if [[ $# -lt 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	echo "Usage: $0 <original_root> <modified_root> [options]"
	echo ""
	echo "Recursively finds .bin files under <modified_root> and runs"
	echo "run_provenance.sh by matching each modified binary name to an"
	echo "original binary under <original_root>."
	exit 0
fi

ORIGINAL_ROOT_RAW="$1"
MODIFIED_ROOT_RAW="$2"
shift 2
EXTRA_ARGS=("$@")

# Resolve relative paths against repo root so invocation works from any cwd.
if [[ "$ORIGINAL_ROOT_RAW" = /* ]]; then
	ORIGINAL_ROOT="$ORIGINAL_ROOT_RAW"
else
	ORIGINAL_ROOT="$REPO_ROOT/$ORIGINAL_ROOT_RAW"
fi

if [[ "$MODIFIED_ROOT_RAW" = /* ]]; then
	MODIFIED_ROOT="$MODIFIED_ROOT_RAW"
else
	MODIFIED_ROOT="$REPO_ROOT/$MODIFIED_ROOT_RAW"
fi

if [[ ! -d "$ORIGINAL_ROOT" ]]; then
	echo "Error: original root does not exist or is not a directory: $ORIGINAL_ROOT" >&2
	exit 1
fi

if [[ ! -d "$MODIFIED_ROOT" ]]; then
	echo "Error: modified root does not exist or is not a directory: $MODIFIED_ROOT" >&2
	exit 1
fi

if [[ ! -x "$RUN_ONE" ]]; then
	echo "Error: missing executable wrapper: $RUN_ONE" >&2
	exit 1
fi

ORIGINAL_ROOT_ABS="$(cd "$ORIGINAL_ROOT" && pwd)"
MODIFIED_ROOT_ABS="$(cd "$MODIFIED_ROOT" && pwd)"

declare -A ORIGINAL_BY_BASENAME
while IFS= read -r -d '' orig_bin; do
	base_name="$(basename "$orig_bin")"
	if [[ -n "${ORIGINAL_BY_BASENAME[$base_name]:-}" ]]; then
		echo "Warning: duplicate original name '$base_name'; using first match: ${ORIGINAL_BY_BASENAME[$base_name]}" >&2
		continue
	fi
	ORIGINAL_BY_BASENAME[$base_name]="$orig_bin"
done < <(find "$ORIGINAL_ROOT_ABS" -type f -name "*.bin" -print0 | sort -z)

processed=0
skipped=0

while IFS= read -r -d '' mod_bin; do
	mod_name="$(basename "$mod_bin")"
	mod_dir="$(dirname "$mod_bin")"

	# Corruption filenames are like DEVICE.mode-severity.bin.
	# We map back to DEVICE.bin in the original root.
	original_stem="${mod_name%%.*}"
	original_name="$original_stem.bin"
	original_bin="${ORIGINAL_BY_BASENAME[$original_name]:-}"

	# Fallback: if the modified filename already matches an original binary name.
	if [[ -z "$original_bin" ]]; then
		original_bin="${ORIGINAL_BY_BASENAME[$mod_name]:-}"
	fi

	if [[ -z "$original_bin" ]]; then
		echo "Skipping (no matching original for modified binary): $mod_bin" >&2
		skipped=$((skipped + 1))
		continue
	fi

	original_dir="$(dirname "$original_bin")"
	out_dir="$mod_dir/figures"
	echo "Original: $original_dir"
	echo "Modified: $mod_dir"
	echo "Binary:   $mod_name -> $(basename "$original_bin")"
	echo "Output:   $out_dir"
	"$RUN_ONE" "$original_dir" "$mod_dir" "$out_dir" "${EXTRA_ARGS[@]}"
	processed=$((processed + 1))
done < <(find "$MODIFIED_ROOT_ABS" \( -type d -name figures -prune \) -o \( -type f -name "*.bin" -print0 \) | sort -z)

echo "Done. Processed $processed modified binaries. Skipped $skipped binaries."

