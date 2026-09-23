#!/bin/bash
# run_fuzzware.sh — run the Fuzzware dynamic-analysis pipeline for a single firmware.
#
# The firmware's directory must contain the Fuzzware artifacts (config.yml, syms.yml,
# base_inputs/, valid_basic_blocks.txt) alongside the binary referenced by config.yml.

set -e

if [ "$#" -lt 2 ] || [ "$#" -gt 4 ]; then
  echo "Usage: $0 <path/workspace/to/binary> <path/workspace/to/output_dir> [run_for DD:HH:MM:SS] [num_fuzzers]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Binary: $1"
echo "Output dir: $2"

DOCKER_ENV_ARGS=()
if [ -n "${3:-}" ]; then
  echo "Run for: $3"
  DOCKER_ENV_ARGS+=(-e "FUZZWARE_RUN_FOR=$3")
fi
if [ -n "${4:-}" ]; then
  echo "Num fuzzers: $4"
  DOCKER_ENV_ARGS+=(-e "FUZZWARE_NUM_FUZZERS=$4")
fi

docker run --rm \
  "${DOCKER_ENV_ARGS[@]}" \
  -v "$REPO_ROOT:/workspace" \
  firmcorr-fuzzware \
  /workspace/$1 \
  /workspace/$2

