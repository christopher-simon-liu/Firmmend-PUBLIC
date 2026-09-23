import argparse
import csv
import importlib
import logging
import math
import os
from pathlib import Path

import numpy as np
from PIL import Image


logger = logging.getLogger(__name__)


def _save_svg_from_rgb(rgb, out_file_path):
	"""Save an RGB numpy image as SVG using matplotlib without axes or padding."""
	try:
		matplotlib = importlib.import_module("matplotlib")
		matplotlib.use("Agg")
		plt = importlib.import_module("matplotlib.pyplot")
	except ImportError:
		logger.warning(
			"matplotlib is not installed; skipping SVG output: %s",
			out_file_path,
		)
		return

	height, width, _ = rgb.shape
	dpi = 100
	fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi, frameon=False)
	ax = fig.add_axes([0, 0, 1, 1])
	ax.imshow(rgb)
	ax.axis("off")
	fig.savefig(out_file_path, format="svg", dpi=dpi, bbox_inches="tight", pad_inches=0)
	plt.close(fig)


def parse_arguments():
	parser = argparse.ArgumentParser(
		prog=os.path.basename(__file__),
		description=(
			"Compute byte-wise (corrupted - mended) differences and render diff figures"
		),
	)
	parser.add_argument("corrupted_binary", help="Path to the corrupted binary")
	parser.add_argument("mended_binary", help="Path to the mended binary")
	parser.add_argument("output_folder", help="Path to output folder")
	parser.add_argument(
		"--width",
		type=int,
		default=512,
		help="Image width in bytes per row (default: 512)",
	)
	return parser.parse_args()


def _load_as_uint8(file_path: Path):
	return np.frombuffer(file_path.read_bytes(), dtype=np.uint8)


def _align_with_ff_padding(corrupted_bytes, mended_bytes):
	max_size = max(corrupted_bytes.size, mended_bytes.size, 1)
	if corrupted_bytes.size < max_size:
		corrupted_bytes = np.pad(
			corrupted_bytes,
			(0, max_size - corrupted_bytes.size),
			mode="constant",
			constant_values=0xFF,
		)
	if mended_bytes.size < max_size:
		mended_bytes = np.pad(
			mended_bytes,
			(0, max_size - mended_bytes.size),
			mode="constant",
			constant_values=0xFF,
		)
	return corrupted_bytes, mended_bytes, max_size


def _shape_2d(arr_1d, width):
	rows = math.ceil(arr_1d.size / width)
	padded = np.pad(
		arr_1d,
		(0, rows * width - arr_1d.size),
		mode="constant",
		constant_values=0,
	)
	return padded.reshape((rows, width))


def _diff_to_rgb(diff):
	"""
	Map signed diff in [-255, 255] to RGB:
	- positive diff: red channel
	- negative diff: blue channel
	- exact zero: black
	"""
	positive = np.clip(diff, 0, 255).astype(np.uint8)
	negative = np.clip(-diff, 0, 255).astype(np.uint8)
	rgb = np.zeros(diff.shape + (3,), dtype=np.uint8)
	rgb[..., 0] = positive
	rgb[..., 2] = negative
	return rgb


def main():
	args = parse_arguments()
	corrupted_path = Path(args.corrupted_binary)
	mended_path = Path(args.mended_binary)
	output_folder = Path(args.output_folder)
	width = args.width

	if width <= 0:
		raise ValueError("--width must be a positive integer")

	corrupted_bytes = _load_as_uint8(corrupted_path)
	mended_bytes = _load_as_uint8(mended_path)

	corrupted_aligned, mended_aligned, max_size = _align_with_ff_padding(
		corrupted_bytes,
		mended_bytes,
	)

	# Compute signed element-wise subtraction: corrupted - mended.
	diff_1d = corrupted_aligned.astype(np.int16) - mended_aligned.astype(np.int16)

	diff_2d = _shape_2d(diff_1d, width)
	rgb_2d = _diff_to_rgb(diff_2d)
	rgb_1d = _diff_to_rgb(diff_1d.reshape(1, max_size))

	output_folder.mkdir(parents=True, exist_ok=True)

	output_stem = corrupted_path.name
	out_png = output_folder / f"{output_stem}.diff.png"
	out_svg = output_folder / f"{output_stem}.diff.svg"
	out_1d_png = output_folder / f"{output_stem}.diff.1d.png"
	out_1d_svg = output_folder / f"{output_stem}.diff.1d.svg"
	out_csv = output_folder / f"{output_stem}.diff.csv"
	out_indexes = output_folder / f"{output_stem}.diff.indexes.csv"

	logger.info("Creating %s", out_png)
	Image.fromarray(rgb_2d, mode="RGB").save(out_png)

	logger.info("Creating %s", out_svg)
	_save_svg_from_rgb(rgb_2d, out_svg)

	logger.info("Creating %s", out_1d_png)
	Image.fromarray(rgb_1d, mode="RGB").save(out_1d_png)

	logger.info("Creating %s", out_1d_svg)
	_save_svg_from_rgb(rgb_1d, out_1d_svg)

	nonzero_indices = np.flatnonzero(diff_1d)

	logger.info("Creating %s", out_csv)
	with out_csv.open("w", newline="", encoding="utf-8") as csv_file:
		writer = csv.writer(csv_file)
		writer.writerow(["index", "corrupted_byte", "mended_byte", "diff"])
		for idx in nonzero_indices:
			corrupted_byte = -1 if idx >= corrupted_bytes.size else int(corrupted_bytes[idx])
			mended_byte = -1 if idx >= mended_bytes.size else int(mended_bytes[idx])
			writer.writerow([
				int(idx),
				corrupted_byte,
				mended_byte,
				int(diff_1d[idx]),
			])

	logger.info("Creating %s", out_indexes)
	with out_indexes.open("w", newline="", encoding="utf-8") as csv_file:
		writer = csv.writer(csv_file)
		writer.writerow(["index"])
		for idx in nonzero_indices:
			writer.writerow([int(idx)])


if __name__ == "__main__":
	main()
