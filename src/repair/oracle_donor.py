import argparse
import csv
from pathlib import Path


def parse_arguments():
	parser = argparse.ArgumentParser(
		description="Create oracle replacement candidates from an original binary"
	)
	parser.add_argument("indexes", help="Path to the index-only CSV file")
	parser.add_argument("binary", help="Path to the corrupted binary file")
	parser.add_argument("original_binary", help="Path to the original binary file")
	parser.add_argument("output_folder", help="Path to the output folder")
	return parser.parse_args()


def load_indexes(indexes_path: Path):
	with indexes_path.open("r", newline="", encoding="utf-8") as csv_file:
		reader = csv.reader(csv_file)
		next(reader, None)
		return [int(row[0]) for row in reader if row]


def main():
	args = parse_arguments()
	indexes_path = Path(args.indexes)
	binary_path = Path(args.binary)
	original_binary_path = Path(args.original_binary)
	output_folder = Path(args.output_folder)

	indexes = load_indexes(indexes_path)
	binary = binary_path.read_bytes()
	original_binary = original_binary_path.read_bytes()

	output_folder.mkdir(parents=True, exist_ok=True)
	output_path = output_folder / f"{binary_path.stem}.oracle_donor.repair.csv"
	with output_path.open("w", newline="", encoding="utf-8") as csv_file:
		writer = csv.writer(csv_file)
		writer.writerow(["index", "corrupted_byte", "candidate_byte"])
		for index in indexes:
			corrupted_byte = (
				binary[index]
				if 0 <= index < len(binary)
				else -1
			)
			candidate_byte = (
				original_binary[index]
				if 0 <= index < len(original_binary)
				else -1
			)
			writer.writerow([index, corrupted_byte, candidate_byte])


if __name__ == "__main__":
	main()