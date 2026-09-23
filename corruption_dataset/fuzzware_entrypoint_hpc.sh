#!/bin/bash
# fuzzware_entrypoint_hpc.sh — HPC-adapted fuzzware_entrypoint.sh
# Changes from original:
#   - WORK_DIR = /output/workdir (no mktemp, no cleanup trap) so fuzzware-project
#     persists at /output/workdir/fuzzware-project/ for post-mortem inspection
#   - FUZZWARE_RUN_FOR defaults to 01:00:00:00 (24hr)
set -e

INPUT_FIRMWARE="$1"
OUTPUT_DIR="$2"

FUZZWARE_RUN_FOR="${FUZZWARE_RUN_FOR:-01:00:00:00}"
FUZZWARE_NUM_FUZZERS="${FUZZWARE_NUM_FUZZERS:-1}"
FUZZWARE_PROJECT_NAME="fuzzware-project"

BINARY_NAME="$(basename "$INPUT_FIRMWARE")"
SRC_DIR="$(dirname "$INPUT_FIRMWARE")"

mkdir -p "$OUTPUT_DIR"

SUMMARY_PATH="$OUTPUT_DIR/${BINARY_NAME}_fuzzware.json"
BLOCKS_PATH="$OUTPUT_DIR/${BINARY_NAME}_fuzzware_blocks.txt"

# Write failure-safe defaults so any crash still leaves machine-readable output
cat > "$SUMMARY_PATH" <<EOF
{
    "binary_name": "$BINARY_NAME",
    "boot_success": 0,
    "num_blocks": 0
}
EOF
: > "$BLOCKS_PATH"

if [ ! -d "$SRC_DIR" ]; then
  echo "ERROR: firmware directory does not exist: $SRC_DIR" >&2
  exit 0
fi

# Fixed workdir inside /output so fuzzware-project survives container exit
WORK_DIR="$OUTPUT_DIR/workdir"
mkdir -p "$WORK_DIR"
rm -rf "$WORK_DIR/$FUZZWARE_PROJECT_NAME"

cp -a "$SRC_DIR/." "$WORK_DIR/"

if [ ! -f "$WORK_DIR/config.yml" ]; then
  echo "ERROR: no config.yml found next to $INPUT_FIRMWARE" >&2
  ls -la "$WORK_DIR" >&2 || true
  exit 0
fi

# Compatibility shim: create symlinks for any binary names referenced in config.yml
# that differ from the actual input binary filename
INPUT_BASENAME="$(basename "$INPUT_FIRMWARE")"
while IFS= read -r cfg_file; do
  [ -z "$cfg_file" ] && continue
  [ -e "$WORK_DIR/$cfg_file" ] && continue
  if [ -e "$WORK_DIR/$INPUT_BASENAME" ]; then
    ln -s "$INPUT_BASENAME" "$WORK_DIR/$cfg_file" 2>/dev/null \
      || cp -f "$WORK_DIR/$INPUT_BASENAME" "$WORK_DIR/$cfg_file"
    echo "WARNING: config.yml referenced missing '$cfg_file'; linked to '$INPUT_BASENAME'." >&2
  fi
done < <(awk -F':' '/^[[:space:]]*file:[[:space:]]*/ {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); if ($2 != "") print $2}' "$WORK_DIR/config.yml" | sort -u)

export AFL_SKIP_CPUFREQ=1
export AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1

PROJ_DIR="$WORK_DIR/$FUZZWARE_PROJECT_NAME"

echo "Running Fuzzware pipeline for $BINARY_NAME (run-for=$FUZZWARE_RUN_FOR, n=$FUZZWARE_NUM_FUZZERS)"
fuzzware pipeline \
  --skip-afl-cpufreq \
  --run-for "$FUZZWARE_RUN_FOR" \
  -n "$FUZZWARE_NUM_FUZZERS" \
  -p "$FUZZWARE_PROJECT_NAME" \
  "$WORK_DIR" || echo "WARNING: 'fuzzware pipeline' returned a non-zero status"

if [ ! -d "$PROJ_DIR" ]; then
  echo "ERROR: Fuzzware project directory was not created; leaving default summary." >&2
  exit 0
fi

echo "Generating coverage traces/statistics"
fuzzware genstats coverage -p "$PROJ_DIR" || echo "WARNING: 'fuzzware genstats' returned a non-zero status"

echo "Collecting unique covered basic blocks"
fuzzware cov -p "$PROJ_DIR" --all-main-dirs -o "$BLOCKS_PATH" || echo "WARNING: 'fuzzware cov' returned a non-zero status"

echo "Writing summary JSON"
python3 /home/user/fuzzware_summary.py "$BINARY_NAME" "$BLOCKS_PATH" "$SUMMARY_PATH"

if [ -d "$PROJ_DIR/stats" ]; then
  rm -rf "$OUTPUT_DIR/${BINARY_NAME}_fuzzware_stats"
  cp -a "$PROJ_DIR/stats" "$OUTPUT_DIR/${BINARY_NAME}_fuzzware_stats" 2>/dev/null || true
fi

echo "Output files:"
ls "$OUTPUT_DIR"
