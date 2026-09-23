import argparse
import importlib
import os
from pathlib import Path
import math
import numpy as np
from PIL import Image
import logging
import csv
import json

logger = logging.getLogger(__name__)


def parse_arguments():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Creates list of bytes to change, given binary and indexes of corrupted bytes",
    )
    parser.add_argument("indexes", help="Path to indexes CSV file")
    parser.add_argument("binary", help="Path to binary file")
    parser.add_argument("output_folder", help="Path to output folder")
    return parser.parse_args()

def main():
    args = parse_arguments()
    indexes_path = Path(args.indexes)
    binary_path = Path(args.binary)
    output_folder = Path(args.output_folder)

    barray = bytearray()
    if binary_path.is_file() and binary_path.suffix == ".bin":
        barray = np.frombuffer(binary_path.read_bytes(), dtype=np.uint8)

    mismatch_indices = []
    with indexes_path.open("r", encoding="utf-8") as csv_file:
        next(csv_file)  # Skip header
        for line in csv_file:
            index = int(line.strip())
            mismatch_indices.append(index)

    csv_file_path = output_folder / f"{binary_path.stem}.zero_fill.repair.csv"
    logger.info(f"Creating {csv_file_path}")
    with csv_file_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["index", "corrupted_byte", "candidate_byte"])
        for idx in mismatch_indices:
            writer.writerow([int(idx), int(barray[idx]), 0])
   


if __name__ == "__main__":
    main()