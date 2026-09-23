#!/usr/bin/env bash
# run_manifest_all.sh — recursively run run_manifest.sh over a tree of mended binaries.
# Usage: ./scripts/run_manifest_all.sh [--parameter KEY=VALUE]...
#            MEND_ROOT CORRUPTED_ROOT ORIGINAL_ROOT [OUTPUT_ROOT]
#
# For each *mend.bin under MEND_ROOT this script finds the corresponding
# corrupted binary in the matching folder under CORRUPTED_ROOT and the ideal
# original binary under ORIGINAL_ROOT, then writes manifest.json next to the
# mended binary, or to OUTPUT_ROOT/<path relative to MEND_ROOT> when given.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
RUN_ONE="$SCRIPT_DIR/run_manifest.sh"

usage() {
	echo "Usage: $0 [--parameter KEY=VALUE]... [MEND_ROOT] [CORRUPTED_ROOT] [ORIGINAL_ROOT] [OUTPUT_ROOT]"
	echo ""
	echo "Recursively finds mended binaries under MEND_ROOT and pairs each one with the"
	echo "corrupted binary in the matching folder under CORRUPTED_ROOT and the"
	echo "matching original binary under ORIGINAL_ROOT."
	echo "MEND_ROOT defaults to repairs."
	echo "CORRUPTED_ROOT defaults to firmcorr/dataset/corruption."
	echo "ORIGINAL_ROOT defaults to firmcorr/dataset/extraction."
	echo "OUTPUT_ROOT defaults to the folder holding each mended binary."
}

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	usage
	exit 0
fi

PARAMETERS=()
POSITIONAL=()

while [[ $# -gt 0 ]]; do
	case "$1" in
		--parameter)
			[[ $# -ge 2 ]] || { usage >&2; exit 2; }
			PARAMETERS+=(--parameter "$2")
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

if [[ ${#POSITIONAL[@]} -gt 4 ]]; then
	echo "Error: expected [MEND_ROOT] [CORRUPTED_ROOT] [ORIGINAL_ROOT] [OUTPUT_ROOT]." >&2
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
ORIGINAL_ROOT_RAW="${POSITIONAL[2]:-firmcorr/dataset/extraction}"

MEND_ROOT="$(resolve_path "$MEND_ROOT_RAW")"
CORRUPTED_ROOT="$(resolve_path "$CORRUPTED_ROOT_RAW")"
ORIGINAL_ROOT="$(resolve_path "$ORIGINAL_ROOT_RAW")"
OUTPUT_ROOT=""
if [[ ${#POSITIONAL[@]} -ge 4 ]]; then
	OUTPUT_ROOT="$(resolve_path "${POSITIONAL[3]}")"
fi

for root in "$MEND_ROOT" "$CORRUPTED_ROOT" "$ORIGINAL_ROOT"; do
	if [[ ! -d "$root" ]]; then
		echo "Error: root does not exist or is not a directory: $root" >&2
		exit 1
	fi
done

MEND_ROOT="$(cd "$MEND_ROOT" && pwd)"
CORRUPTED_ROOT="$(cd "$CORRUPTED_ROOT" && pwd)"
ORIGINAL_ROOT="$(cd "$ORIGINAL_ROOT" && pwd)"

METADATA_FILES=()
while IFS= read -r -d '' metadata_file; do
	METADATA_FILES+=("$metadata_file")
done < <(find "$CORRUPTED_ROOT" -type f -name "Metadata.json" -print0 | sort -z)

declare -A ORIGINAL_BY_BASENAME
while IFS= read -r -d '' orig_bin; do
	base_name="$(basename "$orig_bin")"
	if [[ -n "${ORIGINAL_BY_BASENAME[$base_name]:-}" ]]; then
		echo "Warning: duplicate original name '$base_name'; using ${ORIGINAL_BY_BASENAME[$base_name]}" >&2
		continue
	fi
	ORIGINAL_BY_BASENAME[$base_name]="$orig_bin"
done < <(find "$ORIGINAL_ROOT" -type f -name "*.bin" -print0 | sort -z)

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

find_metadata_json() {
	local corrupted_dir="$1" rel_dir_tail="$2" metadata_json case_prefix case_without_rate baseline_metadata
	metadata_json="$corrupted_dir/Metadata.json"
	if [[ -f "$metadata_json" ]]; then
		printf '%s' "$metadata_json"
		return 0
	fi

	case_without_rate="${rel_dir_tail%_*}"
	case_prefix="${case_without_rate%_*}"
	baseline_metadata="$CORRUPTED_ROOT/${case_prefix}_0.0_baseline/Metadata.json"
	if [[ -n "$case_prefix" && -f "$baseline_metadata" ]]; then
		printf '%s' "$baseline_metadata"
		return 0
	fi

	if [[ ${#METADATA_FILES[@]} -eq 1 ]]; then
		printf '%s' "${METADATA_FILES[0]}"
		return 0
	fi

	return 1
}

processed=0
skipped=0
failed=0

while IFS= read -r -d '' mend_bin; do
	mend_name="$(basename "$mend_bin")"
	mend_dir="$(dirname "$mend_bin")"
	rel_dir="${mend_dir#"$MEND_ROOT"}"
	rel_dir="${rel_dir#/}"
	match_rel_dir="${rel_dir:-$(basename "$mend_dir")}"

	# MEND_ROOT may include a leading method level (repairs/<method>/...).
	if ! corrupted_bin="$(find_corrupted_bin "$CORRUPTED_ROOT/$match_rel_dir")"; then
		corrupted_bin="$(find_corrupted_bin "$CORRUPTED_ROOT/${match_rel_dir#*/}")" || corrupted_bin=""
	fi

	if [[ -z "$corrupted_bin" ]]; then
		echo "Skipping (no matching corrupted binary): $mend_bin" >&2
		skipped=$((skipped + 1))
		continue
	fi

	corrupted_name="$(basename "$corrupted_bin")"
	rel_dir_tail="${match_rel_dir#*/}"
	if [[ "$rel_dir_tail" == "$match_rel_dir" ]]; then
		rel_dir_tail="$match_rel_dir"
	fi
	metadata_json="$(find_metadata_json "$(dirname "$corrupted_bin")" "$rel_dir_tail")" || metadata_json=""
	original_bin="${ORIGINAL_BY_BASENAME[${corrupted_name%%.*}.bin]:-${ORIGINAL_BY_BASENAME[$corrupted_name]:-}}"
	if [[ -z "$original_bin" ]]; then
		echo "Skipping (no matching original binary): $mend_bin" >&2
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
		out_dir="$mend_dir"
	fi

	echo "=== $match_rel_dir/$mend_name -> $out_dir"
	if ! "$RUN_ONE" "$mend_bin" "$corrupted_bin" "$original_bin" "$out_dir" "${PARAMETERS[@]+"${PARAMETERS[@]}"}"; then
		echo "Error: manifest failed for $mend_bin" >&2
		failed=$((failed + 1))
		continue
	fi
	if [[ -n "$metadata_json" ]]; then
		cp "$metadata_json" "$mend_dir/Metadata.json"
	else
		echo "Warning: no Metadata.json next to corrupted binary: $corrupted_bin" >&2
	fi
	processed=$((processed + 1))
done < <(find "$MEND_ROOT" \( -type d -name figures -prune \) -o \( -type f \( -name "*mend.bin" -o -name "*.bin" \) -print0 \) | sort -z)

echo "Done. Wrote $processed manifests. Skipped $skipped. Failed $failed."

if [[ $failed -gt 0 ]]; then
	exit 1
fi
