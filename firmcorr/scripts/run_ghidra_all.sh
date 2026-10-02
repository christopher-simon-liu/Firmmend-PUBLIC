#!/bin/bash

set -e

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <path/workspace/to/input_dir> <path/workspace/to/output_dir>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

to_repo_relative() {
  local input_path="$1"

  case "$input_path" in
    /*)
      case "$input_path" in
        "$REPO_ROOT"/*)
          printf '%s\n' "${input_path#$REPO_ROOT/}"
          ;;
        *)
          echo "Error: path must be inside the repository root: $input_path" >&2
          exit 1
          ;;
      esac
      ;;
    *)
      printf '%s\n' "$input_path"
      ;;
  esac
}

INPUT_DIR_REL="$(to_repo_relative "$1")"
OUTPUT_DIR_REL="$(to_repo_relative "$2")"
INPUT_DIR_ABS="$REPO_ROOT/$INPUT_DIR_REL"
OUTPUT_DIR_ABS="$REPO_ROOT/$OUTPUT_DIR_REL"
INPUT_ROOT_NAME="$(basename "$INPUT_DIR_REL")"

echo "Input dir: $INPUT_DIR_REL"
echo "Output dir: $OUTPUT_DIR_REL"

mkdir -p "$OUTPUT_DIR_ABS"

render_progress_bar() {
  local current="$1"
  local total="$2"
  local width=24
  local percent=0
  local filled=0
  local empty=0
  local filled_bar=""
  local empty_bar=""

  if [ "$total" -gt 0 ]; then
    percent=$(( current * 100 / total ))
    filled=$(( current * width / total ))
  fi
  empty=$(( width - filled ))

  printf -v filled_bar '%*s' "$filled" ''
  printf -v empty_bar '%*s' "$empty" ''
  filled_bar="${filled_bar// /#}"
  empty_bar="${empty_bar// /-}"

  printf '[%s%s] %d/%d (%d%%)' "$filled_bar" "$empty_bar" "$current" "$total" "$percent"
}

TMUX_PROGRESS_ENABLED=0
TMUX_STATUS_RIGHT_OLD=""
if [ -n "${TMUX:-}" ] && command -v tmux >/dev/null 2>&1; then
  TMUX_PROGRESS_ENABLED=1
  TMUX_STATUS_RIGHT_OLD="$(tmux show-options -gv status-right 2>/dev/null || true)"
  restore_tmux_status() {
    tmux set-option -g status-right "$TMUX_STATUS_RIGHT_OLD" >/dev/null 2>&1 || true
  }
  trap restore_tmux_status EXIT INT TERM
fi

mapfile -t BIN_FILES < <(find "$INPUT_DIR_ABS" -type f \( -iname '*.bin' -o -iname '*.BIN' \) | sort)
TOTAL_BINARIES="${#BIN_FILES[@]}"

if [ "$TOTAL_BINARIES" -eq 0 ]; then
  echo "No .bin files found under $INPUT_DIR_REL"
  exit 0
fi

CURRENT_INDEX=0
for bin_path in "${BIN_FILES[@]}"; do
  CURRENT_INDEX=$((CURRENT_INDEX + 1))

  rel_bin_path="${bin_path#$REPO_ROOT/}"
  rel_from_input="${bin_path#$INPUT_DIR_ABS/}"
  rel_bin_dir_from_input="$(dirname "$rel_from_input")"
  bin_name="$(basename "$bin_path")"
  firmware_name="${bin_name%%.*}"

  metadata_path=""
  local_metadata_path="$(dirname "$bin_path")/Metadata.json"
  extraction_metadata_path="$REPO_ROOT/dataset/extraction/$firmware_name/Metadata.json"

  if [ -f "$local_metadata_path" ]; then
    metadata_path="$local_metadata_path"
  elif [ -f "$extraction_metadata_path" ]; then
    metadata_path="$extraction_metadata_path"
  fi

  base_addr_hex=""
  if [ -n "$metadata_path" ]; then
    base_addr_dec="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("flash_start", ""))' "$metadata_path" 2>/dev/null || true)"
    if [[ "$base_addr_dec" =~ ^[0-9]+$ ]]; then
      printf -v base_addr_hex '0x%X' "$base_addr_dec"
    fi
  fi

  if [ "$rel_bin_dir_from_input" = "." ]; then
    rel_out_dir="$OUTPUT_DIR_REL/$INPUT_ROOT_NAME"
  else
    rel_out_dir="$OUTPUT_DIR_REL/$INPUT_ROOT_NAME/$rel_bin_dir_from_input"
  fi

  mkdir -p "$REPO_ROOT/$rel_out_dir"
  expected_summary_path="$REPO_ROOT/$rel_out_dir/${bin_name}_ghidra.json"
  progress_text="$(render_progress_bar "$CURRENT_INDEX" "$TOTAL_BINARIES")"
  if [ "$TMUX_PROGRESS_ENABLED" -eq 1 ]; then
    tmux set-option -g status-right "ghidra $progress_text" >/dev/null 2>&1 || true
  fi

  if [ -f "$expected_summary_path" ]; then
    echo "[$CURRENT_INDEX/$TOTAL_BINARIES] Skipping Ghidra for: $rel_bin_path (already exists: ${expected_summary_path#$REPO_ROOT/})"
    continue
  fi

  echo "[$CURRENT_INDEX/$TOTAL_BINARIES] Running Ghidra for: $rel_bin_path"
  if [ -n "$base_addr_hex" ]; then
    echo "Using base address from Metadata.json ($metadata_path): $base_addr_hex"
    "$SCRIPT_DIR/run_ghidra.sh" "$rel_bin_path" "$rel_out_dir" "$base_addr_hex"
  else
    echo "Metadata base address unavailable; using Ghidra default base"
    "$SCRIPT_DIR/run_ghidra.sh" "$rel_bin_path" "$rel_out_dir"
  fi
done

if [ "$TMUX_PROGRESS_ENABLED" -eq 1 ]; then
  tmux set-option -g status-right "ghidra complete $(render_progress_bar "$TOTAL_BINARIES" "$TOTAL_BINARIES")" >/dev/null 2>&1 || true
fi

echo "Completed Ghidra runs for $TOTAL_BINARIES binaries."

