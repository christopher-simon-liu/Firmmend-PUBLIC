#!/bin/bash

set -e

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "Usage: $0 <path/workspace/to/binary> <path/workspace/to/output_dir> [base_addr_hex]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "Binary: $1"
echo "Output dir: $2"

DOCKER_BASE_ARGS=()
if [ -n "${3:-}" ]; then
  echo "Base addr: $3"
  DOCKER_BASE_ARGS=(-e "GHIDRA_BASE_ADDR=$3")
fi

docker run --rm \
  "${DOCKER_BASE_ARGS[@]}" \
  -v "$REPO_ROOT:/workspace" \
  firmcorr-ghidra \
  /workspace/$1 \
  /workspace/$2

  