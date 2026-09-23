import argparse
import csv
from pathlib import Path


def parse_arguments():
	parser = argparse.ArgumentParser(
		description="Apply repair candidates to a corrupted binary"
	)
	parser.add_argument("repair_csv", help="Path to a repair CSV file")
	parser.add_argument("binary", help="Path to the corrupted binary file")
	parser.add_argument("output_folder", help="Path to the output folder")
	return parser.parse_args()


def apply_repairs(repair_csv: Path, binary: bytearray):
	with repair_csv.open("r", newline="", encoding="utf-8") as csv_file:
		reader = csv.DictReader(csv_file)
		required_columns = {"index", "candidate_byte"}
		if not required_columns.issubset(reader.fieldnames or set()):
			raise ValueError(
				"Repair CSV must contain index and candidate_byte columns"
			)

		provenance_columns = ("original_byte", "corrupted_byte")

		for row_number, row in enumerate(reader, start=2):
			try:
				index = int(row["index"])
				candidate_byte = int(row["candidate_byte"])
			except (KeyError, TypeError, ValueError) as error:
				raise ValueError(
					f"Invalid repair at CSV row {row_number}: {row}"
				) from error

			if candidate_byte != -1 and not 0 <= candidate_byte <= 255:
				raise ValueError(
					f"Candidate byte must be -1 or in the range 0-255 "
					f"at CSV row {row_number}"
				)

			if index < 0:
				raise ValueError(
					f"Repair index {index} is outside the binary at "
					f"CSV row {row_number}"
				)

			if index >= len(binary):
				provenance_value = None
				for column in provenance_columns:
					if column in row and row[column] not in (None, ""):
						try:
							provenance_value = int(row[column])
						except ValueError as error:
							raise ValueError(
								f"Invalid {column} value at CSV row {row_number}: "
								f"{row[column]!r}"
							) from error
						break

				if provenance_value == -1:
					# Partial dumps may truncate the tail; pad unknown bytes with 0xFF.
					binary.extend([0xFF] * (index + 1 - len(binary)))
				else:
					raise ValueError(
						f"Repair index {index} is outside the binary at "
						f"CSV row {row_number}. Add a provenance column "
						f"with -1 for truncated bytes to enable padding."
					)

			if candidate_byte != -1:
				binary[index] = candidate_byte


def main():
	args = parse_arguments()
	repair_csv = Path(args.repair_csv)
	binary_path = Path(args.binary)
	output_folder = Path(args.output_folder)

	binary = bytearray(binary_path.read_bytes())
	apply_repairs(repair_csv, binary)

	output_folder.mkdir(parents=True, exist_ok=True)
	if not repair_csv.name.endswith(".repair.csv"):
		raise ValueError("Repair CSV filename must end with .repair.csv")
	output_name = f"{repair_csv.name[:-len('.repair.csv')]}.mend.bin"
	output_path = output_folder / output_name
	output_path.write_bytes(binary)


if __name__ == "__main__":
	main()
