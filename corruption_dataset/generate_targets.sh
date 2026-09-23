#!/bin/bash
# generate_targets.sh — discover all fuzzware targets under an input directory
# and write their paths (relative to REPO_DIR) to targets.txt.
#
# Mirrors the config.yml discovery logic from run_fuzzware_all.sh, but outputs
# a flat targets.txt suitable for use with the SLURM array job.
#
# Binaries are looked up by searching:
#   1. The config's own directory (config.yml sibling)
#   2. Each parent directory up to REPO_DIR
#   3. dataset/original/<firmware_name>/ (firmcorr layout: corrupted configs,
#      original binaries)
#
# Usage: ./generate_targets.sh <input_dir> [output targets.txt path]
#   input_dir  — absolute path to directory to scan (e.g. /work/liuc1/firmcorr/dataset/corruption)
#   targets.txt — defaults to <input_dir>/../../targets.txt (i.e. REPO_DIR/targets.txt)
#
# REPO_DIR is auto-detected as the repo root (two levels above input_dir by default),
# or set it explicitly: REPO_DIR=/work/liuc1/firmcorr ./generate_targets.sh ...

set -euo pipefail

INPUT_DIR="$(cd "${1:?Usage: $0 <input_dir> [targets.txt]}" && pwd)"

# Auto-detect REPO_DIR: walk up from INPUT_DIR until we find scripts/run_fuzzware.sh
# or fall back to the directory two levels above INPUT_DIR.
if [ -z "${REPO_DIR:-}" ]; then
  _dir="${INPUT_DIR}"
  while [ "${_dir}" != "/" ]; do
    if [ -f "${_dir}/scripts/run_fuzzware.sh" ]; then
      REPO_DIR="${_dir}"
      break
    fi
    _dir="$(dirname "${_dir}")"
  done
  if [ -z "${REPO_DIR:-}" ]; then
    # fallback: two levels up from input dir
    REPO_DIR="$(cd "${INPUT_DIR}/../.." && pwd)"
  fi
fi

TARGETS_FILE="${2:-${REPO_DIR}/targets.txt}"

if [ ! -d "${INPUT_DIR}" ]; then
  echo "Error: input directory not found: ${INPUT_DIR}" >&2
  exit 1
fi

echo "Repo:     ${REPO_DIR}"
echo "Scanning: ${INPUT_DIR}"
echo "Output:   ${TARGETS_FILE}"
echo ""

> "${TARGETS_FILE}"   # truncate/create

FOUND=0
SKIPPED=0

find_binary() {
  local bin_name="$1"
  local config_dir="$2"
  local fw_name="$3"

  # 1. Same directory as config.yml
  if [ -f "${config_dir}/${bin_name}" ]; then
    echo "${config_dir}/${bin_name}"
    return 0
  fi

  # 2. Walk up to REPO_DIR
  local search_dir="${config_dir}"
  while [ "${search_dir}" != "${REPO_DIR}" ] && [ "${search_dir}" != "/" ]; do
    search_dir="$(dirname "${search_dir}")"
    if [ -f "${search_dir}/${bin_name}" ]; then
      echo "${search_dir}/${bin_name}"
      return 0
    fi
  done

  # 3. dataset/original/<firmware_name>/ (firmcorr-specific layout)
  local original="${REPO_DIR}/dataset/original/${fw_name}/${bin_name}"
  if [ -f "${original}" ]; then
    echo "${original}"
    return 0
  fi

  return 1
}

while IFS= read -r config_path; do
  config_dir="$(dirname "${config_path}")"
  # firmware family name = top-level subdir under INPUT_DIR
  fw_name="$(echo "${config_dir#${INPUT_DIR}/}" | cut -d'/' -f1)"

  # Extract binary name from config.yml "file:" entry
  bin_name=$(grep -E '^[[:space:]]*file:[[:space:]]' "${config_path}" 2>/dev/null \
    | head -n1 \
    | sed -E 's/^[[:space:]]*file:[[:space:]]*//; s/[[:space:]]*//')

  if [ -z "${bin_name}" ]; then
    echo "  SKIP (no 'file:' entry): ${config_path#${REPO_DIR}/}"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  if ! find_binary "${bin_name}" "${config_dir}" "${fw_name}" > /dev/null 2>&1; then
    echo "  SKIP (binary not found: ${bin_name}): ${config_path#${REPO_DIR}/}"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  # Write the config directory relative to REPO_DIR
  rel_dir="${config_dir#${REPO_DIR}/}"
  echo "${rel_dir}" >> "${TARGETS_FILE}"
  FOUND=$((FOUND + 1))

done < <(find "${INPUT_DIR}" -type f -name 'config.yml' | sort)

echo ""
echo "Found:   ${FOUND} targets"
echo "Skipped: ${SKIPPED} (missing binary or no file: entry)"
echo ""
echo "targets.txt written to: ${TARGETS_FILE}"
echo ""
echo "Next: update fuzzware_array.slurm line:"
echo "  #SBATCH --array=1-${FOUND}%450"
echo "Then: sbatch fuzzware_array.slurm"

