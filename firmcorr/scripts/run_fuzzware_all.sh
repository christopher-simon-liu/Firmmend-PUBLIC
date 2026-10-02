#!/bin/bash
# run_fuzzware_all.sh — batch wrapper that runs the Fuzzware dynamic-analysis pipeline for
# every firmware configuration found under an input directory.
#
# A firmware is identified by the presence of a Fuzzware config.yml file. The binary to run
# is taken from the config's "file:" entry, and outputs mirror the input directory layout
# (matching the behaviour of run_angr_all.sh / run_ghidra_all.sh).

set -e

if [ "$#" -lt 2 ] || [ "$#" -gt 4 ]; then
  echo "Usage: $0 <path/workspace/to/input_dir> <path/workspace/to/output_dir> [run_for DD:HH:MM:SS] [num_fuzzers]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

RUN_FOR="${3:-}"
NUM_FUZZERS="${4:-}"

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

binary_name_from_config() {
  # Extract the firmware binary file name from a Fuzzware config.yml "file:" entry.
  grep -E '^[[:space:]]*file:[[:space:]]' "$1" 2>/dev/null \
    | head -n1 \
    | sed -E 's/^[[:space:]]*file:[[:space:]]*//; s/[[:space:]]*$//'
}

mapfile -t CONFIG_FILES < <(find "$INPUT_DIR_ABS" -type f -name 'config.yml' | sort)
TOTAL_CONFIGS="${#CONFIG_FILES[@]}"

if [ "$TOTAL_CONFIGS" -eq 0 ]; then
  echo "No Fuzzware config.yml files found under $INPUT_DIR_REL"
  exit 0
fi

CURRENT_INDEX=0
for config_path in "${CONFIG_FILES[@]}"; do
  CURRENT_INDEX=$((CURRENT_INDEX + 1))

  config_dir="$(dirname "$config_path")"
  bin_name="$(binary_name_from_config "$config_path")"

  if [ -z "$bin_name" ]; then
    echo "[$CURRENT_INDEX/$TOTAL_CONFIGS] Skipping (no 'file:' entry in ${config_path#$REPO_ROOT/})"
    continue
  fi

  bin_path="$config_dir/$bin_name"
  if [ ! -f "$bin_path" ]; then
    echo "[$CURRENT_INDEX/$TOTAL_CONFIGS] Skipping (binary not found: ${bin_path#$REPO_ROOT/})"
    continue
  fi

  rel_bin_path="${bin_path#$REPO_ROOT/}"
  rel_config_dir_from_input="${config_dir#$INPUT_DIR_ABS}"
  rel_config_dir_from_input="${rel_config_dir_from_input#/}"

  if [ -z "$rel_config_dir_from_input" ]; then
    rel_out_dir="$OUTPUT_DIR_REL/$INPUT_ROOT_NAME"
  else
    rel_out_dir="$OUTPUT_DIR_REL/$INPUT_ROOT_NAME/$rel_config_dir_from_input"
  fi

  mkdir -p "$REPO_ROOT/$rel_out_dir"
  expected_summary_path="$REPO_ROOT/$rel_out_dir/${bin_name}_fuzzware.json"

  progress_text="$(render_progress_bar "$CURRENT_INDEX" "$TOTAL_CONFIGS")"
  if [ "$TMUX_PROGRESS_ENABLED" -eq 1 ]; then
    tmux set-option -g status-right "fuzzware $progress_text" >/dev/null 2>&1 || true
  fi

  if [ -f "$expected_summary_path" ]; then
    echo "[$CURRENT_INDEX/$TOTAL_CONFIGS] Skipping Fuzzware for: $rel_bin_path (already exists: ${expected_summary_path#$REPO_ROOT/})"
    continue
  fi

  echo "[$CURRENT_INDEX/$TOTAL_CONFIGS] Running Fuzzware for: $rel_bin_path"
  "$SCRIPT_DIR/run_fuzzware.sh" "$rel_bin_path" "$rel_out_dir" "$RUN_FOR" "$NUM_FUZZERS"
done

if [ "$TMUX_PROGRESS_ENABLED" -eq 1 ]; then
  tmux set-option -g status-right "fuzzware complete $(render_progress_bar "$TOTAL_CONFIGS" "$TOTAL_CONFIGS")" >/dev/null 2>&1 || true
fi

echo "Completed Fuzzware runs for $TOTAL_CONFIGS configurations."


