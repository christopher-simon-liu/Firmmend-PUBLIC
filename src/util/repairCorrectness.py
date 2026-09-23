"""Aggregate repair-correctness summaries from RepairCandidate manifests."""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter


CASE_PATTERN = re.compile(r"^(?P<mode>.+)_(?P<severity>\d+(?:\.\d+)?)_(?P<variant>[^/]+)$")
EXPERIMENT_PATTERN = re.compile(r"^E\d+_.+")
REPO_ROOT = Path(__file__).resolve().parents[2]

plt.rcParams.update(
	{
		"font.size": 18,
		"axes.titlesize": 18,
		"axes.labelsize": 18,
		"xtick.labelsize": 18,
		"ytick.labelsize": 18,
		"legend.fontsize": 18,
		"figure.titlesize": 22,
	}
)


def parse_arguments():
	parser = argparse.ArgumentParser(
		description="Aggregate manifest repair correctness and create comparison figures."
	)
	parser.add_argument("manifest_root", help="Root directory searched recursively for manifest.json")
	parser.add_argument("output_folder", help="Directory for CSV summaries and figures")
	return parser.parse_args()


def _case_details(manifest_path: Path):
	for directory in (manifest_path.parent, *manifest_path.parents):
		match = CASE_PATTERN.match(directory.name)
		if match:
			return match.group("mode"), float(match.group("severity")), match.group("variant")
	return "unknown", None, "unknown"


def _progress(current: int, total: int):
	width = 30
	filled = width * current // total if total else width
	bar = "#" * filled + "-" * (width - filled)
	print(f"\rLoading manifests: [{bar}] {current}/{total}", end="", file=sys.stderr, flush=True)
	if current == total:
		print(file=sys.stderr)


def _byte_at(data: bytes, offset: int) -> int:
	return data[offset] if offset < len(data) else -1


def _data_range(metadata_path: Path):
	metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
	data_start = metadata["data_start"]
	data_end = metadata["data_end"]
	flash_start = metadata.get("flash_start", 0)
	if any(not isinstance(value, int) or isinstance(value, bool) for value in (data_start, data_end, flash_start)):
		raise ValueError("data_start, data_end, and flash_start must be integers")

	start = data_start - flash_start
	end = data_end - flash_start
	if start < 0 or end <= start:
		raise ValueError(f"invalid data range [{start}, {end})")
	return start, end


def _path_from_manifest(path_value) -> Path:
	path = Path(path_value)
	return path if path.is_absolute() else REPO_ROOT / path


def _method_name(manifest, mended_path: Path) -> str:
	method_name = manifest.get("method_name", "unknown")
	if method_name != "autoencoder_fill":
		return method_name

	path_parts = mended_path.parts
	try:
		method_index = path_parts.index("autoencoder_fill")
	except ValueError:
		return method_name
	if method_index > 0 and EXPERIMENT_PATTERN.fullmatch(path_parts[method_index - 1]):
		return f"{path_parts[method_index - 1]}_{method_name}"
	return method_name


def _correctness_in_data_range(manifest, manifest_path: Path):
	metadata_path = manifest_path.parent / "Metadata.json"
	parameters = manifest.get("parameters")
	if not metadata_path.is_file():
		raise ValueError(f"missing Metadata.json beside manifest")
	if not isinstance(parameters, dict):
		raise ValueError("missing manifest parameters")

	try:
		mended_path = _path_from_manifest(parameters["mended_binary"])
		corrupted_path = _path_from_manifest(parameters["corrupted_binary"])
		original_path = _path_from_manifest(parameters["original_binary"])
	except KeyError as error:
		raise ValueError(f"missing binary path parameter: {error.args[0]}") from error

	start, end = _data_range(metadata_path)
	mended = mended_path.read_bytes()
	corrupted = corrupted_path.read_bytes()
	original = original_path.read_bytes()
	corrupted_offsets = [
		offset
		for offset in range(start, end)
		if _byte_at(corrupted, offset) != _byte_at(original, offset)
	]
	matching = sum(_byte_at(mended, offset) == _byte_at(original, offset) for offset in corrupted_offsets)
	return len(corrupted_offsets), matching, start, end, mended_path


def load_records(manifest_root: Path):
	records = []
	manifest_paths = sorted(manifest_root.rglob("manifest.json"))
	for index, manifest_path in enumerate(manifest_paths, start=1):
		_progress(index, len(manifest_paths))
		try:
			manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
		except (OSError, json.JSONDecodeError) as error:
			print(f"Warning: skipping unreadable manifest {manifest_path}: {error}")
			continue

		correctness = manifest.get("repair_correctness")
		if not isinstance(correctness, dict):
			print(f"Warning: skipping manifest without repair_correctness: {manifest_path}")
			continue

		try:
			total, matching, data_start, data_end, mended_path = _correctness_in_data_range(manifest, manifest_path)
		except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
			print(f"Warning: skipping manifest without usable metadata and binary paths {manifest_path}: {error}")
			continue

		mode, severity, variant = _case_details(manifest_path)
		records.append(
			{
				"manifest_path": manifest_path.as_posix(),
				"method_name": _method_name(manifest, mended_path),
				"corruption_mode": mode,
				"severity": severity,
				"variant": variant,
				"data_start_offset": data_start,
				"data_end_offset": data_end,
				"total_corrupted_bytes": total,
				"matching_mend_bytes": matching,
				"repair_correctness_ratio": matching / total if total else None,
			}
		)
	return records


def write_csv(path: Path, rows, fieldnames):
	with path.open("w", newline="", encoding="utf-8") as output_file:
		writer = csv.DictWriter(output_file, fieldnames=fieldnames)
		writer.writeheader()
		writer.writerows(rows)


def aggregate(records):
	groups = defaultdict(lambda: {"manifest_count": 0, "total": 0, "matching": 0})
	for record in records:
		if record["severity"] is None:
			continue
		key = (record["method_name"], record["corruption_mode"], record["severity"])
		group = groups[key]
		group["manifest_count"] += 1
		group["total"] += record["total_corrupted_bytes"]
		group["matching"] += record["matching_mend_bytes"]

	return [
		{
			"method_name": method,
			"corruption_mode": mode,
			"severity": severity,
			"manifest_count": group["manifest_count"],
			"total_corrupted_bytes": group["total"],
			"matching_mend_bytes": group["matching"],
			"repair_correctness_ratio": group["matching"] / group["total"] if group["total"] else None,
		}
		for (method, mode, severity), group in sorted(groups.items())
	]


def average_by_method_and_mode(records):
	groups = defaultdict(list)
	for record in records:
		ratio = record["repair_correctness_ratio"]
		if ratio is not None:
			groups[(record["method_name"], record["corruption_mode"])].append(ratio)

	return [
		{
			"method_name": method,
			"corruption_mode": mode,
			"manifest_count": len(ratios),
			"average_repair_correctness_ratio": sum(ratios) / len(ratios),
		}
		for (method, mode), ratios in sorted(groups.items())
	]


def overall_by_method(records):
	groups = defaultdict(lambda: {"total": 0, "matching": 0})
	for record in records:
		groups[record["method_name"]]["total"] += record["total_corrupted_bytes"]
		groups[record["method_name"]]["matching"] += record["matching_mend_bytes"]
	return [
		{
			"method_name": method,
			"total_corrupted_bytes": group["total"],
			"matching_mend_bytes": group["matching"],
			"repair_correctness_ratio": group["matching"] / group["total"] if group["total"] else 0,
		}
		for method, group in sorted(groups.items())
	]


def create_overall_figure(overall, output_folder: Path):
	methods = [row["method_name"] for row in overall]
	ratios = [row["repair_correctness_ratio"] for row in overall]

	figure, axis = plt.subplots(figsize=(max(7, len(methods) * 1.25), 5))
	axis.bar(methods, ratios, color="#1f77b4")
	axis.set_ylim(0, 1)
	axis.set_ylabel("Repair correctness ratio")
	axis.set_title("Overall Repair Correctness by Technique")
	axis.tick_params(axis="x", rotation=30)
	figure.tight_layout()
	figure.savefig(output_folder / "repair_correctness_overall.svg")
	figure.savefig(output_folder / "repair_correctness_overall.pdf")
	plt.close(figure)


def create_mode_overall_figure(averages, output_folder: Path):
	modes = sorted({row["corruption_mode"] for row in averages})
	methods = sorted({row["method_name"] for row in averages})
	ratio_by_method_mode = {
		(row["method_name"], row["corruption_mode"]): row["average_repair_correctness_ratio"]
		for row in averages
	}
	bar_width = 0.8 / len(methods)
	positions = range(len(modes))

	figure, axis = plt.subplots(figsize=(max(11, len(modes) * 1.9), 6.2))
	for index, method in enumerate(methods):
		offset = (index - (len(methods) - 1) / 2) * bar_width
		axis.bar(
			[position + offset for position in positions],
			[ratio_by_method_mode.get((method, mode), 0) for mode in modes],
			width=bar_width,
			label=method,
		)
	axis.set_xticks(
		list(positions),
		[mode.replace("_", " ") for mode in modes],
		rotation=20,
		ha="right",
		rotation_mode="anchor",
	)
	axis.set_ylim(0, 1)
	axis.set_ylabel("Average repair correctness ratio")
	axis.set_title("Repair Correctness by Corruption Mode and Technique", fontsize=22)
	axis.legend()
	figure.tight_layout(rect=(0.02, 0.02, 0.98, 0.94), pad=1.2)
	figure.savefig(output_folder / "repair_correctness_by_mode_overall.svg", bbox_inches="tight", pad_inches=0.2)
	figure.savefig(output_folder / "repair_correctness_by_mode_overall.pdf", bbox_inches="tight", pad_inches=0.2)
	plt.close(figure)


def _severity_rows(aggregates, mode, method):
	return [
		row
		for row in aggregates
		if row["corruption_mode"] == mode
		and row["method_name"] == method
		and row["repair_correctness_ratio"] is not None
	]


def _severity_plot_order(methods):
	baselines = ("oracle_donor", "no_repair")
	return [method for method in baselines if method in methods] + [
		method for method in methods if method not in baselines
	]


def _plot_severity(axis, aggregates, mode, methods, colors, markers):
	severities = sorted({row["severity"] for row in aggregates if row["corruption_mode"] == mode and row["repair_correctness_ratio"] is not None})
	for method in _severity_plot_order(methods):
		rows = _severity_rows(aggregates, mode, method)
		if rows:
			axis.plot(
				[row["severity"] for row in rows],
				[row["repair_correctness_ratio"] for row in rows],
				color=colors[method],
				marker=markers[method],
				markersize=5,
				linewidth=2,
				label=method,
			)
	axis.set_xticks(severities)
	axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
	axis.set_ylim(-0.02, 1.02)
	axis.grid(axis="both", alpha=0.25)


def create_severity_figure(aggregates, output_folder: Path):
	modes = sorted({row["corruption_mode"] for row in aggregates})
	methods = sorted({row["method_name"] for row in aggregates})
	colors = dict(zip(methods, plt.get_cmap("tab10").colors))
	markers = {"autoencoder_fill": "s", "local_fill": "o"}
	marker_cycle = ("^", "D", "P", "X", "v", "<", ">")
	remaining_markers = iter(marker_cycle)
	markers.update({method: next(remaining_markers) for method in methods if method not in markers})
	columns = 2
	rows = (len(modes) + columns - 1) // columns
	figure, axes = plt.subplots(rows, columns, figsize=(13, max(4.5, rows * 4)), squeeze=False, sharey=True)
	for axis, mode in zip(axes.flat, modes):
		_plot_severity(axis, aggregates, mode, methods, colors, markers)
		axis.set_title(mode.replace("_", " ").title())
		axis.set_xlabel("Corruption severity")
		axis.set_ylabel("Repair correctness ratio")
	for axis in axes.flat[len(modes):]:
		axis.remove()
	handles, labels = axes.flat[0].get_legend_handles_labels()
	if handles:
		figure.legend(handles, labels, loc="lower center", ncol=min(3, len(methods)), frameon=False)
	figure.suptitle("Repair Correctness vs. Corruption Severity")
	figure.tight_layout(rect=(0, 0.08, 1, 0.95))
	figure.savefig(output_folder / "repair_correctness_by_severity.svg", bbox_inches="tight")
	figure.savefig(output_folder / "repair_correctness_by_severity.pdf", bbox_inches="tight")
	plt.close(figure)

	for mode in modes:
		figure, axis = plt.subplots(figsize=(8, 5))
		_plot_severity(axis, aggregates, mode, methods, colors, markers)
		axis.set_title(f"Repair Correctness vs. Severity: {mode.replace('_', ' ').title()}")
		axis.set_xlabel("Corruption severity")
		axis.set_ylabel("Repair correctness ratio")
		handles, labels = axis.get_legend_handles_labels()
		if handles:
			axis.legend(handles, labels, ncol=2, frameon=False)
		figure.tight_layout()
		file_stem = f"repair_correctness_{mode}_by_severity"
		figure.savefig(output_folder / f"{file_stem}.svg", bbox_inches="tight")
		figure.savefig(output_folder / f"{file_stem}.pdf", bbox_inches="tight")
		plt.close(figure)


def main():
	args = parse_arguments()
	manifest_root = Path(args.manifest_root)
	output_folder = Path(args.output_folder)
	if not manifest_root.is_dir():
		raise SystemExit(f"Manifest root does not exist or is not a directory: {manifest_root}")

	records = load_records(manifest_root)
	if not records:
		raise SystemExit("No manifests with repair_correctness were found.")

	output_folder.mkdir(parents=True, exist_ok=True)
	write_csv(output_folder / "repair_correctness.csv", records, list(records[0]))
	aggregates = aggregate(records)
	write_csv(output_folder / "repair_correctness_by_mode_severity.csv", aggregates, list(aggregates[0]))
	averages = average_by_method_and_mode(records)
	write_csv(output_folder / "repair_correctness_by_method_mode.csv", averages, list(averages[0]))
	overall = overall_by_method(records)
	write_csv(output_folder / "repair_correctness_overall.csv", overall, list(overall[0]))
	create_overall_figure(overall, output_folder)
	create_mode_overall_figure(averages, output_folder)
	create_severity_figure(aggregates, output_folder)
	print(f"Processed {len(records)} manifests. Wrote results to {output_folder}")


if __name__ == "__main__":
	main()
