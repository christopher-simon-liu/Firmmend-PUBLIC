#!/bin/bash
# build_fuzzware.sh — build the FirmCorr dynamic-analysis (Fuzzware) docker image.
#
# This first ensures the upstream `fuzzware:latest` base image exists (building it from
# source if necessary), then builds the thin `firmcorr-fuzzware` image on top of it.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

FUZZWARE_REPO_URL="${FUZZWARE_REPO_URL:-https://github.com/fuzzware-fuzzer/fuzzware.git}"
# Cloned into the gitignored fuzzware/ directory so build artifacts stay out of git.
FUZZWARE_SRC_DIR="${FUZZWARE_SRC_DIR:-$REPO_ROOT/fuzzware/fuzzware-src}"

# 1. Ensure the upstream fuzzware base image (tag: fuzzware:latest) is available.
if ! docker image inspect fuzzware:latest >/dev/null 2>&1; then
  echo "fuzzware:latest image not found; building it from source."
  if [ ! -d "$FUZZWARE_SRC_DIR/.git" ]; then
    echo "Cloning Fuzzware into $FUZZWARE_SRC_DIR"
    mkdir -p "$(dirname "$FUZZWARE_SRC_DIR")"
    git clone --recurse-submodules "$FUZZWARE_REPO_URL" "$FUZZWARE_SRC_DIR"
  fi
  ( cd "$FUZZWARE_SRC_DIR" && ./build_docker.sh )
else
  echo "Found existing fuzzware:latest image."
fi

# 2. Build the FirmCorr dynamic-analysis image on top of the base.
cd "$REPO_ROOT" && docker build --no-cache -t firmcorr-fuzzware -f Dockerfile.fuzzware .

