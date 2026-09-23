import argparse
import json
from pathlib import Path


def parse_arguments():
	parser = argparse.ArgumentParser(
		description="Pad a firmware image to the flash size declared in metadata"
	)
	parser.add_argument("binary", help="Path to the firmware binary")
	parser.add_argument("metadata", help="Path to the firmware Metadata.json")
	parser.add_argument("output", help="Path for the padded firmware binary")
	return parser.parse_args()


def load_flash_size(metadata_path: Path) -> int:
	with metadata_path.open("r", encoding="utf-8") as metadata_file:
		metadata = json.load(metadata_file)

	flash_size = metadata.get("flash_size")
	if not isinstance(flash_size, int) or isinstance(flash_size, bool) or flash_size <= 0:
		raise ValueError(
			f"Metadata flash_size must be a positive integer: {metadata_path}"
		)
	return flash_size


def pad_to_flash_size(binary: bytes, flash_size: int) -> bytes:
	if len(binary) >= flash_size:
		return binary
	return binary + bytes([0xFF]) * (flash_size - len(binary))


def main():
	args = parse_arguments()
	binary_path = Path(args.binary)
	metadata_path = Path(args.metadata)
	output_path = Path(args.output)

	padded_binary = pad_to_flash_size(
		binary_path.read_bytes(), load_flash_size(metadata_path)
	)
	output_path.parent.mkdir(parents=True, exist_ok=True)
	output_path.write_bytes(padded_binary)


if __name__ == "__main__":
	main()