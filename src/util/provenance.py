import argparse
import csv
import importlib
import os
from pathlib import Path
import math
import numpy as np
from PIL import Image
import logging

logger = logging.getLogger(__name__)


def _save_svg_from_rgb(rgb, out_file_path):
    """Save an RGB numpy image as SVG using matplotlib without axes or padding."""
    try:
        matplotlib = importlib.import_module("matplotlib")
        matplotlib.use("Agg")
        plt = importlib.import_module("matplotlib.pyplot")
    except ImportError:
        logger.warning("matplotlib is not installed; skipping SVG output: %s", out_file_path)
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
        description="Creates Images from Binary Files",
    )
    parser.add_argument("original_folder", help="Path to original folder")
    parser.add_argument("modified_folder", help="Path to modified folder")
    parser.add_argument("output_folder", help="Path to output folder")
    return parser.parse_args()


def load_first_bin(folder: Path):
    for file_path in sorted(folder.iterdir()):
        if file_path.is_file() and file_path.suffix == ".bin":
            return file_path
    raise FileNotFoundError(f"No .bin file found in {folder}")


def load_matching_modified_bin(modified_folder: Path, original_bin: Path) -> Path:
    candidates = sorted(
        file_path
        for file_path in modified_folder.iterdir()
        if file_path.is_file() and file_path.suffix == ".bin"
    )
    if not candidates:
        raise FileNotFoundError(f"No .bin file found in {modified_folder}")

    # Prefer files generated from the same source stem, e.g. Console.partial_write-0.5.bin.
    prefix = f"{original_bin.stem}."
    stem_matches = [path for path in candidates if path.name.startswith(prefix)]
    if len(stem_matches) == 1:
        return stem_matches[0]
    if len(stem_matches) > 1:
        logger.warning(
            "Multiple modified binaries matched %s in %s; using %s",
            original_bin.stem,
            modified_folder,
            stem_matches[0].name,
        )
        return stem_matches[0]

    exact_name_matches = [path for path in candidates if path.name == original_bin.name]
    if exact_name_matches:
        return exact_name_matches[0]

    logger.warning(
        "No modified binary matched %s in %s; using first file %s",
        original_bin.stem,
        modified_folder,
        candidates[0].name,
    )
    return candidates[0]


def load_padded_binary(file_path: Path, width: int):
    barray = np.frombuffer(file_path.read_bytes(), dtype=np.uint8)
    size = len(barray)
    h = math.ceil(size / width)
    padding = width * h - size
    if padding:
        barray = np.pad(barray, (0, padding), mode="constant", constant_values=0xFF)
    return barray.reshape((h, width)), size

def pad_to_shape(arr, target_shape):
    pad_width = []
    for dim in range(len(arr.shape)):
        pad_width.append((0, target_shape[dim] - arr.shape[dim]))
    return np.pad(arr, pad_width, mode='constant', constant_values=-1)


def build_1d_provenance_rgb(original_binary, modified_binary, original_size, modified_size):
    """Build a 1-row provenance RGB image across the byte stream."""
    # Use only real bytes from each file, then pad to compare full lengths.
    original_1d = original_binary.reshape(-1)[:original_size]
    modified_1d = modified_binary.reshape(-1)[:modified_size]

    max_size = max(original_size, modified_size, 1)
    if original_1d.size < max_size:
        original_1d = np.pad(
            original_1d,
            (0, max_size - original_1d.size),
            mode="constant",
            constant_values=0xFF,
        )
    if modified_1d.size < max_size:
        modified_1d = np.pad(
            modified_1d,
            (0, max_size - modified_1d.size),
            mode="constant",
            constant_values=0xFF,
        )

    diff_mask = original_1d != modified_1d
    tail_missing_mask = np.zeros(max_size, dtype=bool)
    if modified_size < original_size:
        tail_missing_mask[modified_size:original_size] = True

    rgb = np.zeros((1, max_size, 3), dtype=np.uint8)
    rgb[0, :, 2] = original_1d
    rgb[0, tail_missing_mask, :] = np.array([255, 255, 0], dtype=np.uint8)
    # Draw red last so true mismatches remain visible.
    rgb[0, diff_mask, :] = np.array([255, 0, 0], dtype=np.uint8)
    return rgb

def main():
    args = parse_arguments()
    original_folder = Path(args.original_folder)
    modified_folder = Path(args.modified_folder)
    output_folder = Path(args.output_folder)

    width = 512
    original_bin = load_first_bin(original_folder)
    modified_bin = load_matching_modified_bin(modified_folder, original_bin)

    original_binary, original_size = load_padded_binary(original_bin, width)
    modified_binary, modified_size = load_padded_binary(modified_bin, width)

    max_rows = max(original_binary.shape[0], modified_binary.shape[0])
    if original_binary.shape[0] < max_rows:
        pad_rows = max_rows - original_binary.shape[0]
        original_binary = np.pad(
            original_binary,
            ((0, pad_rows), (0, 0)),
            mode="constant",
            constant_values=0xFF,
        )
    if modified_binary.shape[0] < max_rows:
        pad_rows = max_rows - modified_binary.shape[0]
        modified_binary = np.pad(
            modified_binary,
            ((0, pad_rows), (0, 0)),
            mode="constant",
            constant_values=0xFF,
        )

    if original_binary.shape != modified_binary.shape:
        modified_binary = pad_to_shape(modified_binary, original_binary.shape)

    diff_mask = original_binary != modified_binary
    tail_missing_mask = np.zeros((max_rows, width), dtype=bool)
    if modified_size < original_size:
        # Bytes in original that no longer exist in a truncated modified file.
        linear_idx = np.arange(max_rows * width).reshape((max_rows, width))
        tail_missing_mask = (linear_idx >= modified_size) & (linear_idx < original_size)

    rgb = np.zeros((max_rows, width, 3), dtype=np.uint8)
    rgb[:, :, 2] = original_binary
    rgb[tail_missing_mask] = np.array([255, 255, 0], dtype=np.uint8)
    # Draw red last so true mismatches are visible even when masks overlap.
    rgb[diff_mask] = np.array([255, 0, 0], dtype=np.uint8)

    output_folder.mkdir(parents=True, exist_ok=True)
    im = Image.fromarray(rgb, mode="RGB")
    out_file_path = output_folder / f"{original_bin.name}.provenance.png"
    logger.info(f"Creating {out_file_path}")
    im.save(out_file_path)

    svg_out_file_path = output_folder / f"{original_bin.name}.provenance.svg"
    logger.info(f"Creating {svg_out_file_path}")
    _save_svg_from_rgb(rgb, svg_out_file_path)

    rgb_1d = build_1d_provenance_rgb(
        original_binary,
        modified_binary,
        original_size,
        modified_size,
    )
    im_1d = Image.fromarray(rgb_1d, mode="RGB")

    out_1d_file_path = output_folder / f"{original_bin.name}.provenance.1d.png"
    logger.info(f"Creating {out_1d_file_path}")
    im_1d.save(out_1d_file_path)

    svg_out_1d_file_path = output_folder / f"{original_bin.name}.provenance.1d.svg"
    logger.info(f"Creating {svg_out_1d_file_path}")
    _save_svg_from_rgb(rgb_1d, svg_out_1d_file_path)

    csv_file_path = output_folder / f"{original_bin.name}.provenance.csv"
    logger.info(f"Creating {csv_file_path}")
    mismatch_indices = np.flatnonzero(diff_mask.reshape(-1))
    original_values = original_binary.reshape(-1)
    modified_values = modified_binary.reshape(-1)
    with csv_file_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["index", "original_byte", "corrupted_byte"])
        for idx in mismatch_indices:
            original_byte = -1 if idx >= original_size else int(original_values[idx])
            corrupted_byte = -1 if idx >= modified_size else int(modified_values[idx])
            writer.writerow([
                int(idx),
                original_byte,
                corrupted_byte,
            ])

    csv_file_path = output_folder / f"{original_bin.name}.indexes.csv"
    logger.info(f"Creating {csv_file_path}")
    with csv_file_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["index"])
        for idx in mismatch_indices:
            writer.writerow([int(idx)])

if __name__ == "__main__":
    main()