#!/usr/bin/env bash
# run_repair.sh - wrapper for the repair methods in src/repair/
# Usage: ./scripts/run_repair.sh --method METHOD [--isa ISA] INPUTS...

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

usage() {
	echo "Usage: $0 --method METHOD [--isa ISA] INDEXES_CSV BINARY [ORIGINAL_BINARY] OUTPUT_FOLDER"
	echo "Methods: no_repair, zero_fill, local_fill, nop_fill, oracle_donor,"
	echo "NOP ISAs: arm, arm-thumb, mips, riscv, x86"
	echo "oracle_donor inputs: INDEXES_CSV CORRUPTED_BINARY ORIGINAL_BINARY OUTPUT_FOLDER"
}

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	usage
	exit 0
fi

if [[ "${1:-}" == "-m" || "${1:-}" == "--method" ]]; then
	if [[ $# -lt 2 ]]; then
		usage >&2
		exit 2
	fi
	METHOD="$2"
	shift 2
else
	echo "Error: --method is required." >&2
	usage >&2
	exit 2
fi

ISA=""
if [[ "${1:-}" == "--isa" ]]; then
	if [[ $# -lt 2 ]]; then
		usage >&2
		exit 2
	fi
	ISA="$2"
	shift 2
fi

case "$METHOD" in
	no_repair|zero_fill|local_fill|nop_fill|oracle_donor)
		REPAIR_SCRIPT="$REPO_ROOT/src/repair/$METHOD.py"
		;;
	*)
		echo "Error: unknown repair method: $METHOD" >&2
		usage >&2
		exit 2
		;;
esac

REWRITE_SCRIPT="$REPO_ROOT/src/util/rewrite.py"
PAD_FLASH_SCRIPT="$REPO_ROOT/src/util/pad_flash.py"

if [[ ! -f "$REPAIR_SCRIPT" ]]; then
	echo "Error: repair method is not implemented: $METHOD" >&2
	exit 2
fi

if [[ "$METHOD" == "oracle_donor" ]]; then
	EXPECTED_ARGS=4
else
	EXPECTED_ARGS=3
fi

if [[ $# -ne "$EXPECTED_ARGS" ]]; then
	echo "Error: expected $EXPECTED_ARGS input paths for $METHOD." >&2
	usage >&2
	exit 2
fi

if [[ "$METHOD" == "nop_fill" && -z "$ISA" ]]; then
	echo "Error: --isa is required when using nop_fill." >&2
	usage >&2
	exit 2
fi

if [[ "$METHOD" != "nop_fill" && -n "$ISA" ]]; then
	echo "Error: --isa is only supported with nop_fill." >&2
	usage >&2
	exit 2
fi

INDEXES_CSV="$1"
BINARY="$2"
if [[ "$METHOD" == "oracle_donor" ]]; then
	ORIGINAL_BINARY="$3"
	OUTPUT_FOLDER="$4"
else
	OUTPUT_FOLDER="$3"
fi

REPAIR_BINARY="$BINARY"
metadata_path="$(dirname "$BINARY")/Metadata.json"
if [[ -f "$metadata_path" ]]; then
	temp_dir="$(mktemp -d)"
	trap 'rm -rf "$temp_dir"' EXIT
	REPAIR_BINARY="$temp_dir/$(basename "$BINARY")"
	python3 "$PAD_FLASH_SCRIPT" "$BINARY" "$metadata_path" "$REPAIR_BINARY"
fi

echo "Repair method:  $METHOD"
echo "Indexes CSV:    $INDEXES_CSV"
echo "Binary:         $BINARY"
if [[ "$REPAIR_BINARY" != "$BINARY" ]]; then
	echo "Padded binary:  $REPAIR_BINARY"
fi
if [[ "$METHOD" == "oracle_donor" ]]; then
	echo "Original binary: $ORIGINAL_BINARY"
fi
echo "Output folder:  $OUTPUT_FOLDER"

cd "$REPO_ROOT"
mkdir -p "$OUTPUT_FOLDER"

if [[ "$METHOD" == "no_repair" ]]; then
	# Trivial repair: the corrupted binary is unchanged, but still emit it
    # using the standard "<name>.<method>.mend.bin" naming so downstream
    # tools (run_diff_all.sh, run_manifest_all.sh) can find it.
    OUT_BIN="$OUTPUT_FOLDER/$(basename "${BINARY%.*}").no_repair.mend.bin"
	cp -f "$REPAIR_BINARY" "$OUT_BIN"
	echo "no_repair: copied $REPAIR_BINARY -> $OUT_BIN"
    exit 0
fi

REPAIR_ARGS=("$INDEXES_CSV" "$REPAIR_BINARY" "$OUTPUT_FOLDER")
if [[ -n "$ISA" ]]; then
	REPAIR_ARGS+=(--isa "$ISA")
elif [[ "$METHOD" == "oracle_donor" ]]; then
	REPAIR_ARGS=("$INDEXES_CSV" "$REPAIR_BINARY" "$ORIGINAL_BINARY" "$OUTPUT_FOLDER")
fi

python3 "$REPAIR_SCRIPT" "${REPAIR_ARGS[@]}"

REPAIR_CSV="$OUTPUT_FOLDER/$(basename "${BINARY%.*}").$METHOD.repair.csv"
if [[ ! -f "$REPAIR_CSV" ]]; then
	echo "Error: repair method did not create $REPAIR_CSV" >&2
	exit 1
fi

exec python3 "$REWRITE_SCRIPT" "$REPAIR_CSV" "$REPAIR_BINARY" "$OUTPUT_FOLDER"
