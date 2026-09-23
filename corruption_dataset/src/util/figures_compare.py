import argparse
import csv
import logging
import re
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D


logger = logging.getLogger(__name__)

MODE_ORDER = {
	"bit_flip": 0,
	"partial_dump": 1,
	"partial_erase": 2,
	"partial_write": 3,
	"address_bit_freeze": 4,
}

MODE_COLORS = {
	"bit_flip": "#4e79a7",
	"partial_dump": "#f28e2b",
	"partial_erase": "#e15759",
	"partial_write": "#76b7b2",
	"address_bit_freeze": "#59a14f",
}

CASE_DIR_PATTERN = re.compile(
	r"^(?P<mode>.+)_(?P<severity>[0-9]*\.?[0-9]+(?:[eE][-+]?\d+)?)_(?P<trial>.+)$"
)


def _to_float(value):
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _normalize_severity(value):
	numeric = _to_float(value)
	if numeric is None:
		return None
	return round(numeric, 6)


def _load_rows(csv_path):
	rows = []
	with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
		reader = csv.DictReader(csv_file)
		for row in reader:
			rows.append(row)
	return rows


def _is_baseline_row(row):
	severity = _normalize_severity(row.get("severity"))
	trial = (row.get("trial") or "").strip().lower()
	return severity == 0.0 or trial == "baseline"


def _instance_key(row):
	firmware = (row.get("firmware") or "").strip()
	mode = (row.get("mode") or "").strip()
	severity = _normalize_severity(row.get("severity"))
	if not firmware or not mode or severity is None:
		return None
	return firmware, mode, severity


def _row_trial(row):
	return (row.get("trial") or "").strip().lower()


def _tool_from_static_metric(static_metric):
	if static_metric.startswith("ghidra_"):
		return "ghidra"
	if static_metric.startswith("angr_"):
		return "angr"
	return None


def _compute_static_retention(static_rows, static_metric):
	baseline_by_firmware_mode = {}
	for row in static_rows:
		key = _instance_key(row)
		if key is None:
			continue
		firmware, mode, _severity = key
		if not _is_baseline_row(row):
			continue
		baseline_value = _to_float(row.get(static_metric))
		if baseline_value is None or baseline_value <= 0:
			continue
		baseline_by_firmware_mode[(firmware, mode)] = baseline_value

	grouped_values = defaultdict(list)
	for row in static_rows:
		key = _instance_key(row)
		if key is None:
			continue
		firmware, mode, _severity = key
		baseline = baseline_by_firmware_mode.get((firmware, mode))
		metric_value = _to_float(row.get(static_metric))
		if baseline is None or metric_value is None:
			continue
		grouped_values[key].append(metric_value / baseline)

	averaged = {}
	for key, values in grouped_values.items():
		if not values:
			continue
		averaged[key] = float(np.mean(values))
	return averaged


def _parse_case_dir(case_dir_name):
	match = CASE_DIR_PATTERN.match(case_dir_name)
	if not match:
		return None
	severity = _normalize_severity(match.group("severity"))
	if severity is None:
		return None
	return match.group("mode"), severity, match.group("trial").lower()


def _normalize_fva(value):
	if value is None:
		return None
	raw = str(value).strip()
	if not raw:
		return None
	try:
		return str(int(raw, 0))
	except (TypeError, ValueError):
		return raw


def _load_function_address_set(functions_csv_path):
	addresses = set()
	with functions_csv_path.open("r", newline="", encoding="utf-8") as csv_file:
		reader = csv.DictReader(csv_file)
		for row in reader:
			addr = _normalize_fva(row.get("fva"))
			if addr is not None:
				addresses.add(addr)
	return addresses


def _scan_function_sets(artifacts_root, tool):
	function_sets = {}
	for csv_path in artifacts_root.rglob(f"*_{tool}_functions.csv"):
		case_dir = csv_path.parent.name
		parsed = _parse_case_dir(case_dir)
		if parsed is None:
			continue
		mode, severity, trial = parsed
		firmware = csv_path.parent.parent.name
		if not firmware:
			continue
		key = (firmware, mode, severity, trial)
		addresses = _load_function_address_set(csv_path)
		if key in function_sets:
			function_sets[key].update(addresses)
		else:
			function_sets[key] = addresses
	return function_sets


def _build_baseline_function_sets(function_sets):
	baseline_by_firmware_mode = {}
	for (firmware, mode, severity, trial), addresses in function_sets.items():
		if not addresses:
			continue
		if severity != 0.0 and trial != "baseline":
			continue
		key = (firmware, mode)
		if key not in baseline_by_firmware_mode or trial == "baseline":
			baseline_by_firmware_mode[key] = addresses
	return baseline_by_firmware_mode


def _compute_static_retention_intersection(static_rows, function_sets):
	baseline_sets = _build_baseline_function_sets(function_sets)
	grouped_values = defaultdict(list)

	for row in static_rows:
		instance_key = _instance_key(row)
		if instance_key is None:
			continue
		firmware, mode, severity = instance_key
		trial = _row_trial(row)
		baseline = baseline_sets.get((firmware, mode))
		if not baseline:
			continue
		current = function_sets.get((firmware, mode, severity, trial))
		if current is None:
			continue
		grouped_values[instance_key].append(len(current.intersection(baseline)) / len(baseline))

	averaged = {}
	for key, values in grouped_values.items():
		if not values:
			continue
		averaged[key] = float(np.mean(values))
	return averaged


def _compute_dynamic_retention(dynamic_rows, dynamic_metric):
	grouped_values = defaultdict(list)
	for row in dynamic_rows:
		key = _instance_key(row)
		if key is None:
			continue
		metric_value = _to_float(row.get(dynamic_metric))
		if metric_value is None:
			continue
		grouped_values[key].append(metric_value)

	averaged = {}
	for key, values in grouped_values.items():
		if not values:
			continue
		averaged[key] = float(np.mean(values))
	return averaged


def _is_unit_ratio(values):
	if not values:
		return True
	return max(values) <= 2.5


def _to_percent_if_ratio(values):
	if _is_unit_ratio(values):
		return [item * 100.0 for item in values]
	return values


def _build_joined_points(static_retention, dynamic_retention):
	keys = sorted(set(static_retention.keys()) & set(dynamic_retention.keys()))
	points = []
	for key in keys:
		firmware, mode, severity = key
		points.append(
			{
				"key": key,
				"firmware": firmware,
				"mode": mode,
				"severity": severity,
				"x": static_retention[key],
				"y": dynamic_retention[key],
			}
		)
	return points


def _mode_sort_key(mode):
	return MODE_ORDER.get(mode, 99), mode


def _mode_legend_handles(modes):
	handles = []
	for mode in modes:
		handles.append(
			Line2D(
				[0],
				[0],
				marker="o",
				linestyle="",
				markersize=7,
				markerfacecolor=MODE_COLORS.get(mode, "#8a8a8a"),
				markeredgecolor="white",
				label=mode.replace("_", " "),
			)
		)
	return handles


def _rankdata(values):
	pairs = sorted(enumerate(values), key=lambda item: item[1])
	ranks = [0.0] * len(values)
	position = 0
	while position < len(pairs):
		start = position
		value = pairs[position][1]
		while position < len(pairs) and pairs[position][1] == value:
			position += 1
		avg_rank = (start + position - 1) / 2.0 + 1.0
		for idx in range(start, position):
			original_index = pairs[idx][0]
			ranks[original_index] = avg_rank
	return ranks


def _pearson_corr(x_values, y_values):
	if len(x_values) < 2 or len(y_values) < 2:
		return None
	x = np.asarray(x_values, dtype=float)
	y = np.asarray(y_values, dtype=float)
	x_std = float(np.std(x))
	y_std = float(np.std(y))
	if x_std == 0.0 or y_std == 0.0:
		return None
	return float(np.corrcoef(x, y)[0, 1])


def _spearman_corr(x_values, y_values):
	if len(x_values) < 2 or len(y_values) < 2:
		return None
	x_rank = _rankdata(x_values)
	y_rank = _rankdata(y_values)
	return _pearson_corr(x_rank, y_rank)


def _format_corr(value):
	if value is None:
		return "NA"
	return f"{value:.3f}"


def _prepare_plot_points(points):
	x_values = _to_percent_if_ratio([point["x"] for point in points])
	y_values = _to_percent_if_ratio([point["y"] for point in points])

	plot_points = []
	for point, x_value, y_value in zip(points, x_values, y_values):
		plot_points.append(
			{
				**point,
				"x_plot": x_value,
				"y_plot": y_value,
			}
		)

	all_values = [point["x_plot"] for point in plot_points] + [point["y_plot"] for point in plot_points]
	axis_min = min(all_values)
	axis_max = max(all_values)
	padding = max((axis_max - axis_min) * 0.08, 2.0)
	low = axis_min - padding
	high = axis_max + padding

	return plot_points, low, high


def _plot_scatter(points, output_path, title):
	plot_points, low, high = _prepare_plot_points(points)

	fig, ax = plt.subplots(figsize=(8.8, 6.4), dpi=160)

	modes = sorted({point["mode"] for point in plot_points}, key=_mode_sort_key)
	for mode in modes:
		mode_points = [point for point in plot_points if point["mode"] == mode]
		ax.scatter(
			[point["x_plot"] for point in mode_points],
			[point["y_plot"] for point in mode_points],
			s=38,
			alpha=0.72,
			label=mode.replace("_", " "),
			color=MODE_COLORS.get(mode, "#8a8a8a"),
			edgecolors="white",
			linewidths=0.5,
		)

	ax.plot([low, high], [low, high], linestyle="--", color="#6d6d6d", linewidth=1.1, alpha=0.8)
	ax.text(
		0.99,
		0.02,
		"y = x",
		transform=ax.transAxes,
		ha="right",
		va="bottom",
		fontsize=18,
		color="#6d6d6d",
	)

	ax.set_xlim(low, high)
	ax.set_ylim(low, high)
	ax.grid(color="#e0e0e0", linewidth=0.8, alpha=0.9)
	ax.set_axisbelow(True)

	# ax.set_title(title, fontsize=14, pad=12)
	ax.set_xlabel("Ghidra Static Retention (%)", fontsize=18)
	ax.set_ylabel("Fuzzware Dynamic Retention (%)", fontsize=18)

	# joined_count = len(plot_points)
	# ax.text(
	# 	0.01,
	# 	0.99,
	# 	f"instances={joined_count}",
	# 	transform=ax.transAxes,
	# 	ha="left",
	# 	va="top",
	# 	fontsize=18,
	# 	color="#555555",
	# )

	legend_handles = _mode_legend_handles(modes)
	ax.legend(handles=legend_handles, title="Corruption Mode", fontsize=18, title_fontsize=18, loc="lower right", frameon=True)

	fig.tight_layout()
	fig.savefig(output_path.with_suffix(".svg"))
	fig.savefig(output_path.with_suffix(".pdf"))
	plt.close(fig)


def _plot_scatter_by_mode(points, output_path, title):
	plot_points, low, high = _prepare_plot_points(points)
	modes = sorted({point["mode"] for point in plot_points}, key=_mode_sort_key)
	if not modes:
		return

	# Stack all mode panels vertically for easier scan/comparison across modes.
	cols = 1
	rows = len(modes)

	fig, axes = plt.subplots(rows, cols, figsize=(6.8, 3.6 * rows), dpi=160)
	if isinstance(axes, np.ndarray):
		axes_flat = axes.ravel()
	else:
		axes_flat = [axes]

	for idx, mode in enumerate(modes):
		ax = axes_flat[idx]
		mode_points = [point for point in plot_points if point["mode"] == mode]
		x_mode = [point["x_plot"] for point in mode_points]
		y_mode = [point["y_plot"] for point in mode_points]
		pearson = _pearson_corr(x_mode, y_mode)
		spearman = _spearman_corr(x_mode, y_mode)
		ax.scatter(
			x_mode,
			y_mode,
			s=40,
			alpha=0.78,
			color=MODE_COLORS.get(mode, "#8a8a8a"),
			edgecolors="white",
			linewidths=0.5,
		)
		ax.plot([low, high], [low, high], linestyle="--", color="#6d6d6d", linewidth=1.0, alpha=0.8)
		ax.set_xlim(low, high)
		ax.set_ylim(low, high)
		ax.grid(color="#e0e0e0", linewidth=0.8, alpha=0.9)
		ax.set_axisbelow(True)
		# ax.set_title(mode.replace("_", " "), fontsize=18)
		ax.text(
			0.02,
			0.98,
			f"n={len(mode_points)}\n"
			f"r={_format_corr(pearson)}\n"
			f"rho={_format_corr(spearman)}",
			transform=ax.transAxes,
			ha="left",
			va="top",
			fontsize=8,
			color="#555555",
		)

	for idx in range(len(modes), len(axes_flat)):
		axes_flat[idx].axis("off")

	for ax in axes_flat[: len(modes)]:
		ax.set_xlabel("Ghidra Static Retention (%)", fontsize=18)
		ax.set_ylabel("Fuzzware Dynamic Retention (%)", fontsize=18)

	legend_handles = _mode_legend_handles(modes)
	fig.legend(
		handles=legend_handles,
		title="Corruption Mode",
		fontsize=18,
		title_fontsize=18,
		loc="upper right",
		frameon=True,
	)

	# fig.suptitle(title, fontsize=14, y=0.995)
	fig.tight_layout(rect=[0, 0, 0.9, 1])
	fig.savefig(output_path.with_suffix(".svg"))
	fig.savefig(output_path.with_suffix(".pdf"))
	plt.close(fig)


def main():
	parser = argparse.ArgumentParser(
		description=(
			"Generate static-vs-dynamic retention scatter plot: Ghidra retention vs Fuzzware retention."
		)
	)
	parser.add_argument(
		"static_csv",
		type=Path,
		help="Path to static results CSV (for example: results/static_results.csv).",
	)
	parser.add_argument(
		"dynamic_csv",
		type=Path,
		help="Path to dynamic results CSV (for example: results/dynamic_results.csv).",
	)
	parser.add_argument(
		"output_dir",
		type=Path,
		help="Directory where figures will be written.",
	)
	parser.add_argument(
		"--static-metric",
		default="ghidra_num_blocks",
		help="Static column used to compute retention ratio against static baseline (default: %(default)s).",
	)
	parser.add_argument(
		"--static-retention-method",
		choices=["count_ratio", "set_intersection"],
		default="count_ratio",
		help=(
			"How to compute static retention: count_ratio = metric/baseline metric; "
			"set_intersection = |baseline function addresses ∩ corrupted function addresses| / |baseline function addresses|."
		),
	)
	parser.add_argument(
		"--static-artifacts-root",
		type=Path,
		default=None,
		help=(
			"Root directory containing per-run static artifacts (defaults to <static_csv_dir>/corruption). "
			"Used when --static-retention-method set_intersection is selected."
		),
	)
	parser.add_argument(
		"--dynamic-metric",
		default="coverage_retention",
		help="Dynamic retention column (default: %(default)s).",
	)
	parser.add_argument(
		"--include-baseline",
		action="store_true",
		help="Include severity 0 baseline points (excluded by default).",
	)
	parser.add_argument(
		"--title",
		default="Static vs Dynamic Retention: Ghidra vs Fuzzware",
		help="Figure title.",
	)
	args = parser.parse_args()

	logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
	args.output_dir.mkdir(parents=True, exist_ok=True)

	static_rows = _load_rows(args.static_csv)
	dynamic_rows = _load_rows(args.dynamic_csv)

	if args.static_retention_method == "count_ratio":
		static_retention = _compute_static_retention(static_rows, args.static_metric)
	else:
		tool = _tool_from_static_metric(args.static_metric)
		if tool is None:
			raise ValueError(
				"set_intersection method requires a static metric prefixed with 'ghidra_' or 'angr_'."
			)
		if not args.static_metric.endswith("_num_functions"):
			raise ValueError(
				"set_intersection currently supports only *_num_functions metrics, because function-address sets are required."
			)

		artifacts_root = args.static_artifacts_root or (args.static_csv.parent / "corruption")
		if not artifacts_root.exists():
			raise FileNotFoundError(f"Static artifacts root does not exist: {artifacts_root}")

		function_sets = _scan_function_sets(artifacts_root, tool)
		if not function_sets:
			raise ValueError(
				f"No {tool} function CSV artifacts found under {artifacts_root} for set_intersection retention."
			)

		static_retention = _compute_static_retention_intersection(static_rows, function_sets)
		logger.info(
			"Computed set-intersection static retention from %d function-artifact instances.",
			len(function_sets),
		)
	dynamic_retention = _compute_dynamic_retention(dynamic_rows, args.dynamic_metric)
	points = _build_joined_points(static_retention, dynamic_retention)

	if not args.include_baseline:
		points = [point for point in points if point["severity"] != 0.0]

	if not points:
		raise ValueError(
			"No overlapping firmware/mode/severity points found between static and dynamic inputs."
		)

	output_path = args.output_dir / "ghidra_vs_fuzzware_static_dynamic_scatter"
	_plot_scatter(points, output_path, args.title)
	mode_output_path = args.output_dir / "ghidra_vs_fuzzware_static_dynamic_scatter_by_mode"
	_plot_scatter_by_mode(points, mode_output_path, f"{args.title} by Corruption Mode")

	logger.info("Saved figure to %s", output_path.with_suffix(".svg"))
	logger.info("Saved figure to %s", output_path.with_suffix(".pdf"))
	logger.info("Saved figure to %s", mode_output_path.with_suffix(".svg"))
	logger.info("Saved figure to %s", mode_output_path.with_suffix(".pdf"))


if __name__ == "__main__":
	main()
