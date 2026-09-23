"""Crop SVG images to a fixed 512x255 viewport.

This utility rewrites SVG files by updating the root ``viewBox`` and
``width``/``height`` attributes. The crop is centered and preserves the
current geometry coordinate system.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

TARGET_WIDTH = 512
TARGET_HEIGHT = 255
TARGET_ASPECT = TARGET_WIDTH / TARGET_HEIGHT


def _parse_number(value: str | None) -> float | None:
	"""Parse a numeric SVG length string and ignore trailing units."""
	if value is None:
		return None
	match = re.match(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)", value)
	if not match:
		return None
	try:
		return float(match.group(1))
	except ValueError:
		return None


def _read_viewbox(root: ET.Element) -> tuple[float, float, float, float] | None:
	view_box = root.attrib.get("viewBox")
	if not view_box:
		return None
	parts = re.split(r"[\s,]+", view_box.strip())
	if len(parts) != 4:
		return None
	try:
		x, y, w, h = (float(part) for part in parts)
	except ValueError:
		return None
	if w <= 0 or h <= 0:
		return None
	return x, y, w, h


def _infer_bounds(root: ET.Element) -> tuple[float, float, float, float] | None:
	existing = _read_viewbox(root)
	if existing is not None:
		return existing

	width = _parse_number(root.attrib.get("width"))
	height = _parse_number(root.attrib.get("height"))
	if width is None or height is None or width <= 0 or height <= 0:
		return None
	return 0.0, 0.0, width, height


def _compute_center_crop(x: float, y: float, width: float, height: float) -> tuple[float, float, float, float]:
	"""Compute crop box with horizontal centering and top vertical anchoring."""
	source_aspect = width / height
	if source_aspect > TARGET_ASPECT:
		crop_height = height
		crop_width = height * TARGET_ASPECT
	else:
		crop_width = width
		crop_height = width / TARGET_ASPECT

	crop_x = x + (width - crop_width) / 2
	# Keep the top section when vertical cropping is needed.
	crop_y = y
	return crop_x, crop_y, crop_width, crop_height


def trim_svg_file(input_path: Path, output_path: Path | None = None, in_place: bool = False) -> Path:
	"""Trim one SVG file to 512x255 and return the written path."""
	if in_place and output_path is not None:
		raise ValueError("Choose either in-place mode or an explicit output path, not both")

	tree = ET.parse(input_path)
	root = tree.getroot()
	bounds = _infer_bounds(root)
	if bounds is None:
		raise ValueError(f"Could not determine bounds for SVG: {input_path}")

	crop_x, crop_y, crop_w, crop_h = _compute_center_crop(*bounds)

	root.set("viewBox", f"{crop_x:.6f} {crop_y:.6f} {crop_w:.6f} {crop_h:.6f}")
	root.set("width", str(TARGET_WIDTH))
	root.set("height", str(TARGET_HEIGHT))

	target = input_path if in_place else (output_path or input_path.with_name(f"{input_path.stem}_trimmed.svg"))
	target.parent.mkdir(parents=True, exist_ok=True)
	tree.write(target, encoding="utf-8", xml_declaration=True)
	return target


def _collect_svg_files(path: Path, recursive: bool) -> list[Path]:
	if path.is_file():
		return [path]
	if recursive:
		return sorted(p for p in path.rglob("*.svg") if p.is_file())
	return sorted(p for p in path.glob("*.svg") if p.is_file())


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Crop SVG images to 512x255")
	parser.add_argument("input", type=Path, help="Input SVG file or directory")
	parser.add_argument("-o", "--output", type=Path, help="Output SVG path (single-file mode only)")
	parser.add_argument("--in-place", action="store_true", help="Overwrite original SVG file(s)")
	parser.add_argument("-r", "--recursive", action="store_true", help="Recurse into subdirectories in directory mode")
	parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
	return parser


def main(argv: list[str] | None = None) -> int:
	parser = _build_parser()
	args = parser.parse_args(argv)

	logging.basicConfig(
		level=logging.INFO if args.verbose else logging.WARNING,
		format="%(levelname)s: %(message)s",
	)

	input_path: Path = args.input
	if not input_path.exists():
		parser.error(f"Input path does not exist: {input_path}")

	if input_path.is_dir() and args.output is not None:
		parser.error("--output is only valid when input is a single file")

	files = _collect_svg_files(input_path, args.recursive)
	if not files:
		parser.error(f"No SVG files found in: {input_path}")

	had_error = False
	for svg_file in files:
		try:
			if svg_file.suffix.lower() != ".svg":
				logger.info("Skipping non-SVG file: %s", svg_file)
				continue
			output_path = args.output if svg_file == input_path else None
			written_path = trim_svg_file(svg_file, output_path=output_path, in_place=args.in_place)
			print(f"trimmed: {svg_file} -> {written_path}")
		except Exception as exc:  # pragma: no cover - defensive CLI handling
			had_error = True
			print(f"error: {svg_file}: {exc}", file=sys.stderr)

	return 1 if had_error else 0


if __name__ == "__main__":
	raise SystemExit(main())
