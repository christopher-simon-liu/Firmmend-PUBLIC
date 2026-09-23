#!/usr/bin/env bash
# run_repair_autoencoder.sh - wrapper for the denoising autoencoder repair
# method in src/repair/denoising_autoencoder/autoencoder_fill.py.
# Usage: ./scripts/run_repair_autoencoder.sh [--model MODEL_PT] [--stride N]
#            [--top-k N] [--batch-size N] INDEXES_CSV BINARY OUTPUT_FOLDER

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

METHOD="autoencoder_fill"
AUTOENCODER_DIR="$REPO_ROOT/src/repair/denoising_autoencoder"
REPAIR_SCRIPT="$AUTOENCODER_DIR/autoencoder_fill.py"
REWRITE_SCRIPT="$REPO_ROOT/src/util/rewrite.py"
PAD_FLASH_SCRIPT="$REPO_ROOT/src/util/pad_flash.py"
DEFAULT_MODEL="$AUTOENCODER_DIR/models/autoencoder.pt"

usage() {
	echo "Usage: $0 [--model MODEL_PT] [--stride N] [--top-k N] [--batch-size N] INDEXES_CSV BINARY OUTPUT_FOLDER"
	echo "MODEL_PT defaults to $DEFAULT_MODEL"
}

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
	usage
	exit 0
fi

MODEL="$DEFAULT_MODEL"
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

if [[ ${#POSITIONAL[@]} -ne 3 ]]; then
	echo "Error: expected INDEXES_CSV BINARY OUTPUT_FOLDER." >&2
	usage >&2
	exit 2
fi

INDEXES_CSV="${POSITIONAL[0]}"
BINARY="${POSITIONAL[1]}"
OUTPUT_FOLDER="${POSITIONAL[2]}"

if [[ ! -f "$REPAIR_SCRIPT" ]]; then
	echo "Error: repair script not found: $REPAIR_SCRIPT" >&2
	exit 2
fi

if [[ ! -f "$MODEL" ]]; then
	echo "Error: model file not found: $MODEL" >&2
	exit 2
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
echo "Model:          $MODEL"
echo "Output folder:  $OUTPUT_FOLDER"

cd "$REPO_ROOT"
mkdir -p "$OUTPUT_FOLDER"

REPAIR_ARGS=("$INDEXES_CSV" "$REPAIR_BINARY" "$MODEL" "$OUTPUT_FOLDER")
if [[ -n "$STRIDE" ]]; then
	REPAIR_ARGS+=(--stride "$STRIDE")
fi
if [[ -n "$TOP_K" ]]; then
	REPAIR_ARGS+=(--top-k "$TOP_K")
fi
if [[ -n "$BATCH_SIZE" ]]; then
	REPAIR_ARGS+=(--batch-size "$BATCH_SIZE")
fi

python3 "$REPAIR_SCRIPT" "${REPAIR_ARGS[@]}"

BIN_STEM="$(basename "${BINARY%.*}")"
REPAIR_CSV="$OUTPUT_FOLDER/$BIN_STEM.$METHOD.repair.csv"
if [[ ! -f "$REPAIR_CSV" ]]; then
	echo "Error: repair method did not create $REPAIR_CSV" >&2
	exit 1
fi

# autoencoder_fill.py writes one row per (index, rank); keep the full ranked
# output for inspection and rewrite the binary using each index's top pick.
RANKED_CSV="$OUTPUT_FOLDER/$BIN_STEM.$METHOD.ranked.csv"
mv -f "$REPAIR_CSV" "$RANKED_CSV"
awk -F',' 'NR==1 || $3=="1"' "$RANKED_CSV" > "$REPAIR_CSV"

exec python3 "$REWRITE_SCRIPT" "$REPAIR_CSV" "$REPAIR_BINARY" "$OUTPUT_FOLDER"
