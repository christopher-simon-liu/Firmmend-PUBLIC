#!/usr/bin/env bash
# run_diff_all.sh — recursively run run_diff.sh over a tree of mended binaries.
# Usage: ./scripts/run_diff_all.sh [--width N] MEND_ROOT CORRUPTED_ROOT [OUTPUT_ROOT]
#
# For each *mend.bin under MEND_ROOT this script finds the corresponding
# corrupted binary in the matching folder under CORRUPTED_ROOT and writes diff
# output to <mend-folder>/figures, or to OUTPUT_ROOT/<path relative to
# MEND_ROOT> when OUTPUT_ROOT is given.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
RUN_ONE="$SCRIPT_DIR/run_diff.sh"

usage() {
	echo "Usage: $0 [--width N] [MEND_ROOT] [CORRUPTED_ROOT] [OUTPUT_ROOT]"
	echo ""
	echo "Recursively finds mended binaries under MEND_ROOT and pairs each one with the"
	echo "corrupted binary in the matching folder under CORRUPTED_ROOT."
	echo "MEND_ROOT defaults to repairs."
	echo "CORRUPTED_ROOT defaults to firmcorr/dataset/corruption."
	echo "OUTPUT_ROOT defaults to <mend-folder>/figures."
}

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	usage
	exit 0
fi

WIDTH=""
POSITIONAL=()

while [[ $# -gt 0 ]]; do
	case "$1" in
		--width)
			[[ $# -ge 2 ]] || { usage >&2; exit 2; }
			WIDTH="$2"
			shift 2
			;;
		-*)
			echo "Error: unknown option: $1" >&2
			usage >&2
			exit 2
			;;
		*)
			POSITIONAL+=("$1")
			shift
			;;
	esac
done

if [[ ${#POSITIONAL[@]} -gt 3 ]]; then
	echo "Error: expected [MEND_ROOT] [CORRUPTED_ROOT] [OUTPUT_ROOT]." >&2
	usage >&2
	exit 2
fi

if [[ ! -x "$RUN_ONE" ]]; then
	echo "Error: missing executable wrapper: $RUN_ONE" >&2
	exit 1
fi

resolve_path() {
	if [[ "$1" = /* ]]; then
		printf '%s' "$1"
	else
		printf '%s' "$REPO_ROOT/$1"
	fi
}

MEND_ROOT_RAW="${POSITIONAL[0]:-repairs}"
CORRUPTED_ROOT_RAW="${POSITIONAL[1]:-firmcorr/dataset/corruption}"

MEND_ROOT="$(resolve_path "$MEND_ROOT_RAW")"
CORRUPTED_ROOT="$(resolve_path "$CORRUPTED_ROOT_RAW")"
OUTPUT_ROOT=""
if [[ ${#POSITIONAL[@]} -ge 3 ]]; then
	OUTPUT_ROOT="$(resolve_path "${POSITIONAL[2]}")"
fi

if [[ ! -d "$MEND_ROOT" ]]; then
	echo "Error: mend root does not exist or is not a directory: $MEND_ROOT" >&2
	exit 1
fi
if [[ ! -d "$CORRUPTED_ROOT" ]]; then
	echo "Error: corrupted root does not exist or is not a directory: $CORRUPTED_ROOT" >&2
	exit 1
fi

MEND_ROOT="$(cd "$MEND_ROOT" && pwd)"
CORRUPTED_ROOT="$(cd "$CORRUPTED_ROOT" && pwd)"

# First .bin directly inside a corruption folder, ignoring figures/ output.
find_corrupted_bin() {
	local dir="$1" candidate
	[[ -d "$dir" ]] || return 1
	for candidate in "$dir"/*.bin; do
		if [[ -f "$candidate" ]]; then
			printf '%s' "$candidate"
			return 0
		fi
	done
	return 1
}

processed=0
skipped=0
failed=0

while IFS= read -r -d '' mend_bin; do
	mend_dir="$(dirname "$mend_bin")"
	rel_dir="${mend_dir#"$MEND_ROOT"}"
	rel_dir="${rel_dir#/}"

	# MEND_ROOT may include a leading method level (repairs/<method>/...).
	if ! corrupted_bin="$(find_corrupted_bin "$CORRUPTED_ROOT/$rel_dir")"; then
		corrupted_bin="$(find_corrupted_bin "$CORRUPTED_ROOT/${rel_dir#*/}")" || corrupted_bin=""
	fi

	if [[ -z "$corrupted_bin" ]]; then
		echo "Skipping (no matching corrupted binary): $mend_bin" >&2
		skipped=$((skipped + 1))
		continue
	fi

	if [[ -n "$OUTPUT_ROOT" ]]; then
		if [[ -n "$rel_dir" ]]; then
			out_dir="$OUTPUT_ROOT/$rel_dir"
		else
			out_dir="$OUTPUT_ROOT"
		fi
	else
		out_dir="$mend_dir/figures"
	fi

	args=("$corrupted_bin" "$mend_bin" "$out_dir")
	if [[ -n "$WIDTH" ]]; then
		args+=(--width "$WIDTH")
	fi

	echo "=== $rel_dir/$(basename "$mend_bin") -> $out_dir"
	if ! "$RUN_ONE" "${args[@]}"; then
		echo "Error: diff failed for $mend_bin" >&2
		failed=$((failed + 1))
		continue
	fi
	processed=$((processed + 1))
done < <(find "$MEND_ROOT" \( -type d -name figures -prune \) -o \( -type f \( -name "*mend.bin" -o -name "*.bin" \) -print0 \) | sort -z)

echo "Done. Diffed $processed binaries. Skipped $skipped. Failed $failed."

if [[ $failed -gt 0 ]]; then
	exit 1
fi
