import argparse
import csv
from pathlib import Path


def parse_arguments():
	parser = argparse.ArgumentParser(
		description="Create local-average replacement candidates for corrupted bytes"
	)
	parser.add_argument("indexes", help="Path to the index-only CSV file")
	parser.add_argument("binary", help="Path to the corrupted binary file")
	parser.add_argument("output_folder", help="Path to the output folder")
	return parser.parse_args()


def load_indexes(indexes_path: Path):
	with indexes_path.open("r", newline="", encoding="utf-8") as csv_file:
		reader = csv.reader(csv_file)
		next(reader, None)
		return [int(row[0]) for row in reader if row]


def build_candidate_bytes(indexes, binary):
	corrupted_indexes = set(indexes)
	candidates = {}

	for index in indexes:
		if index < 0 or index >= len(binary):
			candidates[index] = -1
			continue

		left = index - 1
		while left >= 0 and left in corrupted_indexes:
			left -= 1

		right = index + 1
		while right < len(binary) and right in corrupted_indexes:
			right += 1

		if left < 0 or right >= len(binary):
			candidates[index] = -1
			continue

		candidates[index] = (binary[left] + binary[right]) // 2

	return candidates


def main():
	args = parse_arguments()
	indexes_path = Path(args.indexes)
	binary_path = Path(args.binary)
	output_folder = Path(args.output_folder)

	indexes = load_indexes(indexes_path)
	binary = binary_path.read_bytes()
	candidate_bytes = build_candidate_bytes(indexes, binary)

	output_folder.mkdir(parents=True, exist_ok=True)
	output_path = output_folder / f"{binary_path.stem}.local_fill.repair.csv"
	with output_path.open("w", newline="", encoding="utf-8") as csv_file:
		writer = csv.writer(csv_file)
		writer.writerow(["index", "corrupted_byte", "candidate_byte"])
		for index in indexes:
			corrupted_byte = (
				binary[index]
				if 0 <= index < len(binary)
				else -1
			)
			writer.writerow([index, corrupted_byte, candidate_bytes[index]])


if __name__ == "__main__":
	main()
