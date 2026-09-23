import argparse
import csv
from pathlib import Path


NOP_BYTES = {
	"arm": bytes.fromhex("00 00 A0 E1"),
	"arm-thumb": bytes.fromhex("00 BF"),
	"mips": bytes.fromhex("00 00 00 00"),
	"riscv": bytes.fromhex("13 00 00 00"),
	"x86": bytes.fromhex("90"),
}


def parse_arguments():
	parser = argparse.ArgumentParser(
		description="Create ISA-aware NOP replacement candidates for corrupted bytes"
	)
	parser.add_argument("indexes", help="Path to the index-only CSV file")
	parser.add_argument("binary", help="Path to the corrupted binary file")
	parser.add_argument("output_folder", help="Path to the output folder")
	parser.add_argument(
		"--isa",
		required=True,
		choices=sorted(NOP_BYTES),
		help="Instruction set architecture used to select the NOP encoding",
	)
	return parser.parse_args()


def load_indexes(indexes_path: Path):
	with indexes_path.open("r", newline="", encoding="utf-8") as csv_file:
		reader = csv.reader(csv_file)
		next(reader, None)
		return [int(row[0]) for row in reader if row]


def build_candidate_bytes(indexes, nop_encoding):
	"""Return NOP bytes only for complete consecutive groups."""
	group_size = len(nop_encoding)
	candidates = {index: -1 for index in indexes}
	unique_indexes = sorted(set(indexes))

	if not unique_indexes:
		return candidates

	run_start = 0
	for position in range(1, len(unique_indexes) + 1):
		is_run_end = (
			position == len(unique_indexes)
			or unique_indexes[position] != unique_indexes[position - 1] + 1
		)
		if not is_run_end:
			continue

		run = unique_indexes[run_start:position]
		for group_start in range(0, len(run) - group_size + 1, group_size):
			group = run[group_start:group_start + group_size]
			for byte_offset, index in enumerate(group):
				candidates[index] = nop_encoding[byte_offset]
		run_start = position

	return candidates


def main():
	args = parse_arguments()
	indexes_path = Path(args.indexes)
	binary_path = Path(args.binary)
	output_folder = Path(args.output_folder)
	nop_encoding = NOP_BYTES[args.isa]
	binary = binary_path.read_bytes()
	indexes = load_indexes(indexes_path)
	candidate_bytes = build_candidate_bytes(indexes, nop_encoding)

	output_folder.mkdir(parents=True, exist_ok=True)
	output_path = output_folder / f"{binary_path.stem}.nop_fill.repair.csv"
	with output_path.open("w", newline="", encoding="utf-8") as csv_file:
		writer = csv.writer(csv_file)
		writer.writerow(["index", "corrupted_byte", "candidate_byte"])
		for index in indexes:
			corrupted_byte = binary[index] if index < len(binary) else -1
			candidate_byte = candidate_bytes[index]
			if corrupted_byte == -1:
				candidate_byte = -1
			writer.writerow([index, corrupted_byte, candidate_byte])


if __name__ == "__main__":
	main()
