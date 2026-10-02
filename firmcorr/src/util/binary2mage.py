import argparse
import importlib
import os
from pathlib import Path
import math
import numpy as np
from PIL import Image
import logging

logger = logging.getLogger(__name__)


def _save_svg_from_gray(gray, out_file_path):
    """Save a grayscale numpy image as SVG without axes/padding."""
    try:
        matplotlib = importlib.import_module("matplotlib")
        matplotlib.use("Agg")
        plt = importlib.import_module("matplotlib.pyplot")
    except ImportError:
        logger.warning("matplotlib is not installed; skipping SVG output: %s", out_file_path)
        return

    height, width = gray.shape
    dpi = 100
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi, frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(gray, cmap="gray", vmin=0, vmax=255)
    ax.axis("off")
    fig.savefig(out_file_path, format="svg", dpi=dpi, bbox_inches="tight", pad_inches=0)
    plt.close(fig)

def parse_arguments():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Creates Images from Binary Files",
    )
    parser.add_argument("binary_folder", help="Path to binary folder")
    parser.add_argument("output_folder", help="Path to output folder")
    return parser.parse_args()

def main():
    args = parse_arguments()
    directory_path = Path(args.binary_folder)
    output_folder = Path(args.output_folder)

    for file_path in directory_path.iterdir():

        if file_path.is_file() and file_path.suffix == ".bin":
            barray = np.frombuffer(file_path.read_bytes(), dtype=np.uint8)
            size = len(barray)
            w = 512 # bytes per row
            h = math.ceil(size / w)
            padding = w * h - size

            if padding:
                barray = np.pad(barray, (0, padding), mode="constant", constant_values=0xFF)

            array = barray.reshape((h, w))

            im = Image.fromarray(array, mode='L')
            # im = im.resize((128,128), resample=Image.NEAREST)

            out_file_path = output_folder / f"{file_path.name}.png"
            logger.info(f"Creating {out_file_path}")
            im.save(out_file_path)

            svg_out_file_path = output_folder / f"{file_path.name}.svg"
            logger.info(f"Creating {svg_out_file_path}")
            _save_svg_from_gray(array, svg_out_file_path)

if __name__ == "__main__":
    main()