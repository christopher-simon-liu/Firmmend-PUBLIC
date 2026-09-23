import argparse
from pathlib import Path


MAIN_PREFIX = "main"
FUZZER_GLOB = "fuzzers/fuzzer*"
TRACE_DIR = "traces"
CRASH_TRACE_DIR = "crash_traces"
BBLSET_PREFIX = "bblset_"
VALID_BB_FILENAME = "valid_basic_blocks.txt"


def log_progress(message):
	print(f"[calcFuzzCoverage] {message}")


def parse_bbl_set_file(trace_path):
	covered = set()
	with trace_path.open("r", encoding="utf-8", errors="ignore") as trace_file:
		for line in trace_file:
			stripped = line.strip()
			if not stripped or stripped.startswith("#"):
				continue
			covered.add(int(stripped, 16))
	return covered


def main_dirs_for_project(project_dir):
	return sorted(path for path in project_dir.glob(f"{MAIN_PREFIX}*") if path.is_dir())


def latest_main_dir(project_dir):
	main_dirs = main_dirs_for_project(project_dir)
	if not main_dirs:
		raise FileNotFoundError(f"No main session directories found under: {project_dir}")
	return main_dirs[-1]


def bblset_trace_paths_for_main(main_dir, crashes=False):
	trace_dir = CRASH_TRACE_DIR if crashes else TRACE_DIR
	pattern = f"{FUZZER_GLOB}/{trace_dir}/{BBLSET_PREFIX}*"
	return sorted(path for path in main_dir.glob(pattern) if path.is_file())


def parse_valid_bb_file(valid_bb_path):
	valid_bbs = set()
	with valid_bb_path.open("r", encoding="utf-8", errors="ignore") as valid_file:
		for line in valid_file:
			stripped = line.strip()
			if not stripped or stripped.startswith("#"):
				continue
			valid_bbs.add(int(stripped, 16))
	return valid_bbs


def valid_bbs_for_project(project_dir):
	data_valid = project_dir / "data" / VALID_BB_FILENAME
	if data_valid.is_file():
		return parse_valid_bb_file(data_valid)

	parent_valid = project_dir.parent / VALID_BB_FILENAME
	if parent_valid.is_file():
		return parse_valid_bb_file(parent_valid)

	return None


def collect_covered_basic_blocks(project_dir, all_main_dirs=False, crashes=False):
	if all_main_dirs:
		main_dirs = main_dirs_for_project(project_dir)
		if not main_dirs:
			raise FileNotFoundError(f"No main session directories found under: {project_dir}")
		log_progress(f"Using all main directories ({len(main_dirs)} total)")
	else:
		main_dirs = [latest_main_dir(project_dir)]
		log_progress(f"Using latest main directory only: {main_dirs[0].name}")

	covered = set()
	for index, main_dir in enumerate(main_dirs, start=1):
		trace_paths = bblset_trace_paths_for_main(main_dir, crashes=crashes)
		log_progress(
			f"Processing {main_dir.name} ({index}/{len(main_dirs)}): "
			f"{len(trace_paths)} trace files"
		)
		for trace_path in trace_paths:
			covered.update(parse_bbl_set_file(trace_path))
		log_progress(f"Running unique basic blocks: {len(covered)}")

	valid_bbs = valid_bbs_for_project(project_dir)
	if valid_bbs is not None:
		before_filter_count = len(covered)
		covered &= valid_bbs
		log_progress(
			f"Applied valid basic block filter: {before_filter_count} -> {len(covered)}"
		)
	else:
		log_progress("No valid_basic_blocks.txt filter found; using raw covered set")

	return covered


def dump_cov_plain(covered_bbs, outfile_path):
	with outfile_path.open("w", encoding="utf-8") as outfile:
		outfile.write("\n".join(f"{bb:x}" for bb in sorted(covered_bbs)))


def parse_arguments():
	parser = argparse.ArgumentParser(
		description=(
			"Collect covered basic blocks from a fuzzware-project directory and "
			"write a fuzzware-compatible plain coverage file."
		)
	)
	parser.add_argument(
		"project_dir",
		help="Path to a fuzzware-project directory (contains mainXXX directories)",
	)
	parser.add_argument(
		"-o",
		"--outfile",
		default="fuzzware_blocks.txt",
		help="Output file path (default: fuzzware_blocks.txt)",
	)
	parser.add_argument(
		"--all-main-dirs",
		action="store_true",
		help="Collect from all mainXXX directories (default: latest only)",
	)
	parser.add_argument(
		"--crashes",
		action="store_true",
		help="Collect from crash_traces instead of traces",
	)
	return parser.parse_args()


def main():
	args = parse_arguments()
	project_dir = Path(args.project_dir)
	if not project_dir.is_dir():
		raise FileNotFoundError(f"Project directory does not exist: {project_dir}")

	log_progress(f"Project directory: {project_dir}")
	log_progress(f"Crash traces mode: {'enabled' if args.crashes else 'disabled'}")

	covered = collect_covered_basic_blocks(
		project_dir,
		all_main_dirs=args.all_main_dirs,
		crashes=args.crashes,
	)

	outfile = Path(args.outfile)
	outfile.parent.mkdir(parents=True, exist_ok=True)
	log_progress(f"Writing output file: {outfile}")
	dump_cov_plain(covered, outfile)

	log_progress(f"Done. Wrote {len(covered)} covered basic blocks to {outfile}")


if __name__ == "__main__":
	main()
