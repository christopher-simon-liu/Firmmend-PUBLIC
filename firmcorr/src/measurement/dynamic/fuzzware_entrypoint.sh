#!/bin/bash
# fuzzware_entrypoint.sh — FirmCorr dynamic-analysis entrypoint.
#
# Runs the Fuzzware fuzzing pipeline for a single firmware image and emits:
#   <binary>_fuzzware.json        : { binary_name, boot_success, num_blocks }
#   <binary>_fuzzware_blocks.txt  : sorted list of unique covered basic blocks (bare hex)
#   <binary>_fuzzware_stats/      : copied pipeline statistics (best-effort)
#
# The firmware's directory must contain the Fuzzware configuration (config.yml, syms.yml),
# the base_inputs/ seed directory and the valid_basic_blocks.txt ground-truth listing.
set -e

INPUT_FIRMWARE="$1"
OUTPUT_DIR="$2"

# Pipeline runtime (DD:HH:MM:SS) and number of local fuzzer instances.
FUZZWARE_RUN_FOR="${FUZZWARE_RUN_FOR:-00:00:10:00}"
FUZZWARE_NUM_FUZZERS="${FUZZWARE_NUM_FUZZERS:-1}"
FUZZWARE_PROJECT_NAME="fuzzware-project"

BINARY_NAME="$(basename "$INPUT_FIRMWARE")"
SRC_DIR="$(dirname "$INPUT_FIRMWARE")"

mkdir -p "$OUTPUT_DIR"

SUMMARY_PATH="$OUTPUT_DIR/${BINARY_NAME}_fuzzware.json"
BLOCKS_PATH="$OUTPUT_DIR/${BINARY_NAME}_fuzzware_blocks.txt"

# Write failure-safe defaults first so that any later failure still leaves machine-readable
# output behind (mirrors the static angr/ghidra entrypoints).
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

# Fuzzware writes its project directory next to config.yml and needs a writable target dir.
# Copy the firmware's Fuzzware artifacts into a temporary working directory so that the
# read-mostly mounted dataset is left untouched.
WORK_DIR="$(mktemp -d)"
cleanup() { rm -rf "$WORK_DIR"; }
trap cleanup EXIT

cp -a "$SRC_DIR/." "$WORK_DIR/"
# Never carry over a previous project from the dataset copy.
rm -rf "$WORK_DIR/$FUZZWARE_PROJECT_NAME"

if [ ! -f "$WORK_DIR/config.yml" ]; then
  echo "ERROR: no config.yml found next to $INPUT_FIRMWARE; cannot run Fuzzware." >&2
  ls -la "$WORK_DIR" >&2 || true
  exit 0
fi

# Compatibility shim: some corruption datasets rename the binary file (for example,
# Drone.address_bit_freeze-0.5.bin) while config.yml still points to the original
# base filename (for example, Drone.bin). Create symlink aliases in the temp workdir
# so Fuzzware can resolve configured paths without mutating dataset files.
INPUT_BASENAME="$(basename "$INPUT_FIRMWARE")"
while IFS= read -r cfg_file; do
  [ -z "$cfg_file" ] && continue
  [ -e "$WORK_DIR/$cfg_file" ] && continue
  if [ -e "$WORK_DIR/$INPUT_BASENAME" ]; then
    ln -s "$INPUT_BASENAME" "$WORK_DIR/$cfg_file" 2>/dev/null || cp -f "$WORK_DIR/$INPUT_BASENAME" "$WORK_DIR/$cfg_file"
    echo "WARNING: config.yml referenced missing '$cfg_file'; linked it to '$INPUT_BASENAME' in temp workspace." >&2
  fi
done < <(awk -F':' '/^[[:space:]]*file:[[:space:]]*/ {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); if ($2 != "") print $2}' "$WORK_DIR/config.yml" | sort -u)

# Quiet AFL's environment checks (Fuzzware does not crash the emulator process).
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

# Ensure all basic-block-set traces exist, then collect the unique covered basic blocks
# (intersected with valid_basic_blocks.txt found at "$PROJ_DIR/../valid_basic_blocks.txt").
echo "Generating coverage traces/statistics"
fuzzware genstats coverage -p "$PROJ_DIR" || echo "WARNING: 'fuzzware genstats' returned a non-zero status"

echo "Collecting unique covered basic blocks"
fuzzware cov -p "$PROJ_DIR" --all-main-dirs -o "$BLOCKS_PATH" || echo "WARNING: 'fuzzware cov' returned a non-zero status"

echo "Writing summary"
python3 /home/user/fuzzware_summary.py "$BINARY_NAME" "$BLOCKS_PATH" "$SUMMARY_PATH"

# Best-effort: keep the pipeline statistics next to the outputs for later inspection.
if [ -d "$PROJ_DIR/stats" ]; then
  rm -rf "$OUTPUT_DIR/${BINARY_NAME}_fuzzware_stats"
  cp -a "$PROJ_DIR/stats" "$OUTPUT_DIR/${BINARY_NAME}_fuzzware_stats" 2>/dev/null || true
fi

ls "$OUTPUT_DIR"
