#!/usr/bin/env bash
# run_repair_autoencoder_all.sh — recursively run run_repair_autoencoder.sh
# over a corrupted-binary tree.
# Usage: ./scripts/run_repair_autoencoder_all.sh [--model MODEL_PT]
#            [--stride N] [--top-k N] [--batch-size N]
#            [INPUT_ROOT] [REPAIRS_ROOT]
#
# For each .bin under INPUT_ROOT this script locates the matching
# *.indexes.csv (in the binary's folder or its figures/ subfolder) and writes
# repair output to REPAIRS_ROOT/autoencoder_fill/<path relative to INPUT_ROOT>.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
RUN_ONE="$SCRIPT_DIR/run_repair_autoencoder.sh"
METHOD="autoencoder_fill"

usage() {
	echo "Usage: $0 [--model MODEL_PT] [--stride N] [--top-k N] [--batch-size N] [INPUT_ROOT] [REPAIRS_ROOT]"
	echo "INPUT_ROOT defaults to firmcorr/dataset/corruption."
	echo "REPAIRS_ROOT defaults to <repo>/repairs."
}

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	usage
	exit 0
fi

MODEL=""
STRIDE=""
TOP_K=""
BATCH_SIZE=""
POSITIONAL=()

while [[ $# -gt 0 ]]; do
	case "$1" in
		--model)
			[[ $# -ge 2 ]] || { usage >&2; exit 2; }
			MODEL="$2"
			shift 2
			;;
		--stride)
			[[ $# -ge 2 ]] || { usage >&2; exit 2; }
			STRIDE="$2"
			shift 2
			;;
		--top-k)
			[[ $# -ge 2 ]] || { usage >&2; exit 2; }
			TOP_K="$2"
			shift 2
			;;
		--batch-size)
			[[ $# -ge 2 ]] || { usage >&2; exit 2; }
			BATCH_SIZE="$2"
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

	args=()
	if [[ -n "$MODEL" ]]; then
		args+=(--model "$MODEL")
	fi
	if [[ -n "$STRIDE" ]]; then
		args+=(--stride "$STRIDE")
	fi
	if [[ -n "$TOP_K" ]]; then
		args+=(--top-k "$TOP_K")
	fi
	if [[ -n "$BATCH_SIZE" ]]; then
		args+=(--batch-size "$BATCH_SIZE")
	fi
	args+=("$indexes_csv" "$bin_path" "$out_dir")

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
