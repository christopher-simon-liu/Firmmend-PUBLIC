#!/bin/bash
set -e

INPUT_FIRMWARE="$1"
OUTPUT_DIR="$2"
FUNCTION_SET="${3:-}"

GHIDRA_PROCESSOR="${GHIDRA_PROCESSOR:-ARM:LE:32:v8-m}"
GHIDRA_BASE_ADDR="${GHIDRA_BASE_ADDR:-0x08000000}"

mkdir -p "$OUTPUT_DIR"

BINARY_NAME="$(basename "$INPUT_FIRMWARE")"
SUMMARY_PATH="$OUTPUT_DIR/${BINARY_NAME}_ghidra.json"

# Default summary is written first so failures still leave machine-readable output.
cat > "$SUMMARY_PATH" <<EOF
{
	"binary_name": "$BINARY_NAME",
	"disassembly_success": 0,
	"num_functions": 0,
	"num_edges": 0,
	"num_nodes": 0
}
EOF


run_headless() {
	local -a command=()
	command=(
		"$GHIDRA_PATH"
		"$GHIDRA_PROJS"
		"GHIDRA_TEMP_PROJ"
		"-scriptPath"
		"$GHIDRA_SCRIPTS"
		"-postScript"
		"$GHIDRA_SCRIPT_ACFG_DISASM"
		"${INPUT_FIRMWARE#/}"
		"$OUTPUT_DIR"
	)

	if [ -n "$FUNCTION_SET" ]; then
		command+=("$FUNCTION_SET")
	fi

	shift 0
	command+=("$@")

	echo "Executing ${command[*]}..."
	"${command[@]}"
}

case "${INPUT_FIRMWARE##*.}" in
	bin|BIN)
		run_headless \
			"-import" \
			"$INPUT_FIRMWARE" \
			"-loader" \
			"BinaryLoader" \
			"-loader-blockName" \
			"$BINARY_NAME" \
			"-processor" \
			"$GHIDRA_PROCESSOR" \
			"-loader-baseAddr" \
			"$GHIDRA_BASE_ADDR" \
			"-readonly"
		;;
	*)
		run_headless \
			"-import" \
			"$INPUT_FIRMWARE" \
			"-readonly" || {
				echo "AutoImporter failed, retrying with BinaryLoader fallback..."
				run_headless \
					"-import" \
					"$INPUT_FIRMWARE" \
					"-loader" \
					"BinaryLoader" \
					"-loader-blockName" \
					"$BINARY_NAME" \
					"-processor" \
					"$GHIDRA_PROCESSOR" \
					"-loader-baseAddr" \
					"$GHIDRA_BASE_ADDR" \
					"-readonly"
			}
		;;
esac

ls "$OUTPUT_DIR"
