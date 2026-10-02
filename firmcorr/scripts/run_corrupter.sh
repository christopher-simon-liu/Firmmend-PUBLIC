#!/usr/bin/env bash
# run_corrupter.sh — wrapper for src/corruption/corrupter.py
# Usage: ./scripts/run_corrupter.sh MODE SEVERITY START END INPUT OUTPUT RANDOM_SEED
# Additional options are passed through unchanged to corrupter.py.
# Run with -h or --help to see all available options.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
CORRUPTER="$REPO_ROOT/src/corruption/corrupter.py"

if [[ $# -lt 7 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    echo "Usage: $0 <mode> <severity> <start> <end> <input> <output> <random_seed> [options]"
    python3 "$CORRUPTER" --help
    exit 0
fi

MODE="$1"
SEVERITY="$2"
START="$3"
END="$4"
INPUT="$5"
OUTPUT="$6"
RANDOM_SEED="$7"
shift 7

echo "Mode:    $MODE"
echo "Severity: $SEVERITY"
echo "Start:   $START"
echo "End:     $END"
echo "Input:   $INPUT"
echo "Output:  $OUTPUT"
echo "Seed:    $RANDOM_SEED"

cd "$REPO_ROOT"
exec python3 "$CORRUPTER" --mode "$MODE" --severity "$SEVERITY" --firmware-start "$START" --firmware-end "$END" --input-binary "$INPUT" --output-folder "$OUTPUT" --random-seed "$RANDOM_SEED" "$@"

