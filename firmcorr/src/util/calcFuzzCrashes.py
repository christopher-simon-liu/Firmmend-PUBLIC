import argparse
import hashlib
import json
import re
from pathlib import Path


MAIN_PREFIX = "main"
FUZZER_GLOB = "fuzzers/fuzzer*"
CRASH_DIR = "crashes"
TRACE_DIR = "traces"
BBLSET_PREFIX = "bblset_"


def log_progress(message):
    print(f"[calcFuzzCrashes] {message}")


def parse_bbl_set_file(trace_path):
    covered = []
    with trace_path.open("r", encoding="utf-8", errors="ignore") as trace_file:
        for line in trace_file:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            covered.append(int(stripped, 16))
    return covered


def main_dirs_for_project(project_dir):
    return sorted(path for path in project_dir.glob(f"{MAIN_PREFIX}*") if path.is_dir())


def latest_main_dir(project_dir):
    main_dirs = main_dirs_for_project(project_dir)
    if not main_dirs:
        raise FileNotFoundError(f"No main session directories found under: {project_dir}")
    return main_dirs[-1]


def crash_input_paths_for_main(main_dir):
    pattern = f"{FUZZER_GLOB}/{CRASH_DIR}/*"
    return sorted(path for path in main_dir.glob(pattern) if path.is_file())


def parse_metadata_value(name, key):
    match = re.search(rf"{re.escape(key)}\D*([0-9A-Fa-f]+)", name)
    if not match:
        return None
    return match.group(1)


def build_trace_index(trace_dir):
    """Build a dict mapping crash IDs to trace file paths for fast lookup."""
    index = {}
    if not trace_dir.is_dir():
        return index
    
    for trace_path in trace_dir.glob(f"{BBLSET_PREFIX}*"):
        trace_id = parse_metadata_value(trace_path.name, "id")
        if trace_id:
            index[trace_id] = trace_path
    return index


def trace_path_for_crash(crash_path, trace_index):
    crash_id = parse_metadata_value(crash_path.name, "id")
    if not crash_id:
        return None
    return trace_index.get(crash_id)


def signature_for_blocks(blocks):
    normalized = "\n".join(f"{bb:x}" for bb in sorted(set(blocks))).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def collect_crash_stats(project_dir, all_main_dirs=False):
    if all_main_dirs:
        main_dirs = main_dirs_for_project(project_dir)
        if not main_dirs:
            raise FileNotFoundError(f"No main session directories found under: {project_dir}")
        log_progress(f"Using all main directories ({len(main_dirs)} total)")
    else:
        main_dirs = [latest_main_dir(project_dir)]
        log_progress(f"Using latest main directory only: {main_dirs[0].name}")

    total_traces = 0
    unique_signatures = set()
    unique_crash_blocks = set()
    unreadable_files = []

    for index, main_dir in enumerate(main_dirs, start=1):
        crash_paths = crash_input_paths_for_main(main_dir)
        
        # Build trace index once per main_dir for O(1) lookups
        trace_dir = list(main_dir.glob(f"{FUZZER_GLOB}"))
        if trace_dir:
            trace_index_dir = trace_dir[0].parent / TRACE_DIR
        else:
            trace_index_dir = None
        trace_index = build_trace_index(trace_index_dir) if trace_index_dir else {}
        
        log_progress(
            f"Processing {main_dir.name} ({index}/{len(main_dirs)}): "
            f"{len(crash_paths)} crash input files, {len(trace_index)} indexed traces"
        )

        for crash_path in crash_paths:
            if crash_path.name.lower() == "readme.txt":
                continue

            total_traces += 1

            crash_sig = parse_metadata_value(crash_path.name, "sig")
            if crash_sig is not None:
                unique_signatures.add(crash_sig)

            trace_path = trace_path_for_crash(crash_path, trace_index)
            if trace_path is None:
                continue

            try:
                blocks = parse_bbl_set_file(trace_path)
            except OSError as exc:
                unreadable_files.append({"path": str(trace_path), "error": str(exc)})
                continue

            if crash_sig is None:
                unique_signatures.add(signature_for_blocks(blocks))
            if blocks:
                unique_crash_blocks.add(blocks[-1])

        log_progress(
            "Running totals: "
            f"traces={total_traces}, "
            f"unique_signatures={len(unique_signatures)}, "
            f"unique_crash_blocks={len(unique_crash_blocks)}"
        )

    return {
        "total_crash_traces": total_traces,
        "unique_crash_signatures": len(unique_signatures),
        "unique_crash_blocks": len(unique_crash_blocks),
        "crash_signature_set": sorted(unique_signatures),
        "crash_block_set": sorted(unique_crash_blocks),
        "unreadable_trace_files": unreadable_files,
    }


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Count crashes from a fuzzware-project directory by reading bblset_* "
            "files under crash_traces."
        )
    )
    parser.add_argument(
        "project_dir",
        help="Path to a fuzzware-project directory (contains mainXXX directories)",
    )
    parser.add_argument(
        "-o",
        "--outfile",
        default="fuzzware_crashes.json",
        help="Output JSON path (default: fuzzware_crashes.json)",
    )
    parser.add_argument(
        "--all-main-dirs",
        action="store_true",
        help="Collect from all mainXXX directories (default: latest only)",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    project_dir = Path(args.project_dir)
    if not project_dir.is_dir():
        raise FileNotFoundError(f"Project directory does not exist: {project_dir}")

    log_progress(f"Project directory: {project_dir}")
    stats = collect_crash_stats(project_dir, all_main_dirs=args.all_main_dirs)

    outfile = Path(args.outfile)
    outfile.parent.mkdir(parents=True, exist_ok=True)

    with outfile.open("w", encoding="utf-8") as ofile:
        json.dump(stats, ofile, indent=4, sort_keys=True)

    log_progress(f"Writing output file: {outfile}")
    log_progress(
        "Done. "
        f"traces={stats['total_crash_traces']}, "
        f"unique_signatures={stats['unique_crash_signatures']}, "
        f"unique_crash_blocks={stats['unique_crash_blocks']}"
    )


if __name__ == "__main__":
    main()