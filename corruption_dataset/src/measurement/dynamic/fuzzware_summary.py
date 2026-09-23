import argparse
import json
import os


def load_basic_block_set(blocks_path):
    """Load unique basic block addresses from a coverage file.

    The file produced by `fuzzware cov` contains one bare hexadecimal basic block
    address per line. Empty lines and comment lines are ignored.
    """
    if not os.path.isfile(blocks_path):
        return set()

    blocks = set()
    with open(blocks_path, "r", encoding="utf-8", errors="ignore") as blocks_file:
        for line in blocks_file:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            blocks.add(stripped)
    return blocks


def count_basic_blocks(blocks_path):
    """Count unique basic blocks listed in a coverage file."""
    return len(load_basic_block_set(blocks_path))


def save_fuzzware_summary(
    json_ofp,
    binary_name="",
    num_blocks=0,
    baseline_blocks=None,
    retained_blocks=None,
):
    """Save the dynamic-analysis summary fields into a JSON file.

    boot_success is a coverage-based heuristic: the firmware is considered to have
    booted successfully if the pipeline produced any unique covered basic blocks.
    """
    summary = {}
    if os.path.isfile(json_ofp):
        try:
            with open(json_ofp, "r", encoding="utf-8") as ifile:
                summary = json.load(ifile)
        except (OSError, json.JSONDecodeError):
            summary = {}

    summary.update(
        {
            "binary_name": binary_name,
            "boot_success": 1 if num_blocks > 0 else 0,
            "num_blocks": num_blocks,
        }
    )
    if baseline_blocks is not None:
        summary["baseline_blocks"] = baseline_blocks
        summary["corrupted_blocks"] = num_blocks
        summary["coverage_ratio"] = (
            num_blocks / baseline_blocks if baseline_blocks > 0 else 0.0
        )
        if retained_blocks is not None:
            summary["coverage_retention"] = (
                retained_blocks / baseline_blocks if baseline_blocks > 0 else 0.0
            )

    with open(json_ofp, "w", encoding="utf-8") as ofile:
        ofile.write(json.dumps(summary, indent=4, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description="Summarize Fuzzware coverage output")
    parser.add_argument("binary_name", type=str, help="Name of the firmware binary")
    parser.add_argument("blocks_file", type=str, help="Path to the covered basic blocks file")
    parser.add_argument("summary_file", type=str, help="Path to the summary JSON to write")
    parser.add_argument(
        "baseline_blocks_file",
        nargs="?",
        default=None,
        help="Optional path to valid_basic_blocks.txt for baseline denominator",
    )
    args = parser.parse_args()

    corrupted_block_set = load_basic_block_set(args.blocks_file)
    num_blocks = len(corrupted_block_set)
    baseline_blocks = None
    retained_blocks = None
    if args.baseline_blocks_file:
        baseline_block_set = load_basic_block_set(args.baseline_blocks_file)
        baseline_blocks = len(baseline_block_set)
        retained_blocks = len(corrupted_block_set.intersection(baseline_block_set))

    save_fuzzware_summary(
        args.summary_file,
        binary_name=args.binary_name,
        num_blocks=num_blocks,
        baseline_blocks=baseline_blocks,
        retained_blocks=retained_blocks,
    )


if __name__ == "__main__":
    main()
