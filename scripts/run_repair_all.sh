#!/usr/bin/env bash
# run_repair_all.sh — recursively run run_repair.sh over a corrupted-binary tree.
# Usage: ./scripts/run_repair_all.sh --method METHOD [--isa ISA]
#            [--original-root DIR] INPUT_ROOT [REPAIRS_ROOT]
#
# For each .bin under INPUT_ROOT this script locates the matching
# *.indexes.csv (in the binary's folder or its figures/ subfolder) and writes
# repair output to REPAIRS_ROOT/METHOD/<path relative to INPUT_ROOT>.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
RUN_ONE="$SCRIPT_DIR/run_repair.sh"

usage() {
	echo "Usage: $0 --method METHOD [--isa ISA] [--original-root DIR] [INPUT_ROOT] [REPAIRS_ROOT]"
	echo "Methods: no_repair, zero_fill, local_fill, nop_fill, oracle_donor,"
	echo "         adjacent_coloration, direct_transplanting, generative_inpainting"
	echo "NOP ISAs: arm, arm-thumb, mips, riscv, x86"
	echo "INPUT_ROOT defaults to firmcorr/dataset/corruption."
	echo "--original-root defaults to firmcorr/dataset/extraction for oracle_donor."
	echo "REPAIRS_ROOT defaults to <repo>/repairs."
}

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	usage
	exit 0
fi

METHOD=""
ISA=""
ORIGINAL_ROOT_RAW=""
POSITIONAL=()

while [[ $# -gt 0 ]]; do
	case "$1" in
		-m|--method)
			[[ $# -ge 2 ]] || { usage >&2; exit 2; }
			METHOD="$2"
			shift 2
			;;
		--isa)
			[[ $# -ge 2 ]] || { usage >&2; exit 2; }
			ISA="$2"
			shift 2
			;;
		--original-root)
			[[ $# -ge 2 ]] || { usage >&2; exit 2; }
			ORIGINAL_ROOT_RAW="$2"
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

if [[ -z "$METHOD" ]]; then
	echo "Error: --method is required." >&2
	usage >&2
	exit 2
fi

if [[ ${#POSITIONAL[@]} -gt 2 ]]; then
	echo "Error: expected [INPUT_ROOT] [REPAIRS_ROOT]." >&2
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

INPUT_ROOT_RAW="${POSITIONAL[0]:-firmcorr/dataset/corruption}"
REPAIRS_ROOT_RAW="${POSITIONAL[1]:-repairs}"

INPUT_ROOT="$(resolve_path "$INPUT_ROOT_RAW")"
REPAIRS_ROOT="$(resolve_path "$REPAIRS_ROOT_RAW")"

if [[ ! -d "$INPUT_ROOT" ]]; then
	echo "Error: input root does not exist or is not a directory: $INPUT_ROOT" >&2
	exit 1
fi
INPUT_ROOT="$(cd "$INPUT_ROOT" && pwd)"

declare -A ORIGINAL_BY_BASENAME
if [[ "$METHOD" == "oracle_donor" ]]; then
	if [[ -z "$ORIGINAL_ROOT_RAW" ]]; then
		ORIGINAL_ROOT_RAW="firmcorr/dataset/extraction"
	fi
	ORIGINAL_ROOT="$(resolve_path "$ORIGINAL_ROOT_RAW")"
	if [[ ! -d "$ORIGINAL_ROOT" ]]; then
		echo "Error: original root does not exist or is not a directory: $ORIGINAL_ROOT" >&2
		exit 1
	fi
	ORIGINAL_ROOT="$(cd "$ORIGINAL_ROOT" && pwd)"
	while IFS= read -r -d '' orig_bin; do
		base_name="$(basename "$orig_bin")"
		if [[ -n "${ORIGINAL_BY_BASENAME[$base_name]:-}" ]]; then
			echo "Warning: duplicate original name '$base_name'; using ${ORIGINAL_BY_BASENAME[$base_name]}" >&2
			continue
		fi
		ORIGINAL_BY_BASENAME[$base_name]="$orig_bin"
	done < <(find "$ORIGINAL_ROOT" -type f -name "*.bin" -print0 | sort -z)
elif [[ -n "$ORIGINAL_ROOT_RAW" ]]; then
	echo "Error: --original-root is only supported with oracle_donor." >&2
	usage >&2
	exit 2
fi

# First *.indexes.csv found in the binary's folder, then in figures/.
find_indexes_csv() {
	local dir="$1" candidate
	for candidate in "$dir"/*.indexes.csv "$dir"/figures/*.indexes.csv; do
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

while IFS= read -r -d '' bin_path; do
	bin_name="$(basename "$bin_path")"
	bin_dir="$(dirname "$bin_path")"
	rel_dir="${bin_dir#"$INPUT_ROOT"}"
	rel_dir="${rel_dir#/}"

	if ! indexes_csv="$(find_indexes_csv "$bin_dir")"; then
		echo "Skipping (no *.indexes.csv near binary): $bin_path" >&2
		skipped=$((skipped + 1))
		continue
	fi

	if [[ -n "$rel_dir" ]]; then
		out_dir="$REPAIRS_ROOT/$METHOD/$rel_dir"
	else
		out_dir="$REPAIRS_ROOT/$METHOD"
	fi

	args=(--method "$METHOD")
	if [[ -n "$ISA" ]]; then
		args+=(--isa "$ISA")
	fi
	args+=("$indexes_csv" "$bin_path")

	if [[ "$METHOD" == "oracle_donor" ]]; then
		original_bin="${ORIGINAL_BY_BASENAME[${bin_name%%.*}.bin]:-${ORIGINAL_BY_BASENAME[$bin_name]:-}}"
		if [[ -z "$original_bin" ]]; then
			echo "Skipping (no matching original binary): $bin_path" >&2
			skipped=$((skipped + 1))
			continue
		fi
		args+=("$original_bin")
	fi

	args+=("$out_dir")

	echo "=== $rel_dir/$bin_name -> $out_dir"
	mkdir -p "$out_dir"
	if ! "$RUN_ONE" "${args[@]}"; then
		echo "Error: repair failed for $bin_path" >&2
		failed=$((failed + 1))
		continue
	fi
	processed=$((processed + 1))
done < <(find "$INPUT_ROOT" \( -type d -name figures -prune \) -o \( -type f -name "*.bin" -print0 \) | sort -z)

echo "Done. Repaired $processed binaries. Skipped $skipped. Failed $failed."

if [[ $failed -gt 0 ]]; then
	exit 1
fi
