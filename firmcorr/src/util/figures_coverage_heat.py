import argparse
import csv
import logging
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


logger = logging.getLogger(__name__)

MODE_ORDER = {
	"bit_flip": 0,
	"partial_dump": 1,
	"partial_erase": 2,
	"partial_write": 3,
	"address_bit_freeze": 4,
}

METRIC_CONFIG = {
	"coverage_ratio": {
		"title": "Per-Firmware Heatmap of Coverage Ratio",
		# "colorbar": "Coverage Ratio (%)",
		"output_stem": "dynamic_coverage_ratio_per_firmware_heatmap",
	},
	"crash_ratio": {
		"title": "Per-Firmware Heatmap of Crash Ratio",
		# "colorbar": "Crash Ratio (%)",
		"output_stem": "dynamic_crash_ratio_per_firmware_heatmap",
	},
}


def _to_float(value):
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _load_rows(csv_path):
	rows = []
	with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
		reader = csv.DictReader(csv_file)
		for row in reader:
			rows.append(row)
	return rows


def _severity_sort_value(value):
	numeric = _to_float(value)
	if numeric is None:
		return float("inf")
	return numeric


def _mode_sort_key(mode):
	return MODE_ORDER.get(mode, 99), mode


def _column_sort_key(column):
	mode, severity = column
	return (_mode_sort_key(mode), _severity_sort_value(severity))


def _is_ratio_unit_scale(values):
	if not values:
		return True
	return max(values) <= 2.5


def _as_percent_if_ratio(values):
	if _is_ratio_unit_scale(values):
		return [item * 100.0 for item in values]
	return values


def _build_matrix(rows, metric, include_baseline):
	grouped = defaultdict(list)
	firmwares = set()
	columns = set()

	for row in rows:
		firmware = (row.get("firmware") or "").strip()
		mode = (row.get("mode") or "").strip()
		severity_raw = (row.get("severity") or "").strip()
		severity_value = _severity_sort_value(severity_raw)

		if not firmware or not mode:
			continue
		if not include_baseline and severity_value == 0.0:
			continue

		# Keep firmware/column axes complete even when the chosen metric is missing.
		firmwares.add(firmware)
		columns.add((mode, severity_raw))

		value = _to_float(row.get(metric))
		if value is None:
			continue

		key = (firmware, mode, severity_raw)
		grouped[key].append(value)

	if not firmwares or not columns:
		return [], [], np.empty((0, 0)), np.empty((0, 0), dtype=bool)

	firmware_list = sorted(firmwares)
	column_list = sorted(columns, key=_column_sort_key)
	firmware_index = {name: idx for idx, name in enumerate(firmware_list)}
	column_index = {name: idx for idx, name in enumerate(column_list)}

	matrix = np.full((len(firmware_list), len(column_list)), np.nan, dtype=float)
	for (firmware, mode, severity_raw), values in grouped.items():
		row_idx = firmware_index[firmware]
		col_idx = column_index[(mode, severity_raw)]
		matrix[row_idx, col_idx] = float(np.mean(values))

	flat = [value for value in matrix[~np.isnan(matrix)]]
	flat_percent = _as_percent_if_ratio(flat)
	scale_factor = 100.0 if flat and flat_percent and abs(flat_percent[0] - flat[0]) > 1e-12 else 1.0
	if scale_factor == 100.0:
		matrix *= 100.0

	missing_mask = np.isnan(matrix)
	return firmware_list, column_list, matrix, missing_mask


def _column_labels(columns):
	labels = []
	for mode, severity in columns:
		labels.append(f"{mode.replace('_', ' ')}\nsev={severity}")
	return labels


def _draw_heatmap(firmwares, columns, matrix, missing_mask, output_path, title, colorbar_label):
	if matrix.size == 0:
		raise ValueError("No valid matrix values found to plot.")

	valid_values = matrix[~missing_mask]
	vmin = float(np.nanpercentile(valid_values, 5))
	vmax = float(np.nanpercentile(valid_values, 95))
	if vmin == vmax:
		vmin -= 1.0
		vmax += 1.0

	row_count = len(firmwares)
	col_count = len(columns)
	width = max(10.5, col_count * 0.42)
	height = max(5.8, row_count * 0.38 + 2.0)

	fig = plt.figure(figsize=(width, height), dpi=160, constrained_layout=True)
	grid = fig.add_gridspec(nrows=2, ncols=1, height_ratios=[5.0, 1.2], hspace=0.06)

	ax_heat = fig.add_subplot(grid[0])
	ax_spread = fig.add_subplot(grid[1], sharex=ax_heat)

	cmap = plt.get_cmap("RdYlGn").copy()
	cmap.set_bad(color="#d9d9d9")

	image = ax_heat.imshow(
		np.ma.array(matrix, mask=missing_mask),
		aspect="auto",
		interpolation="nearest",
		cmap=cmap,
		vmin=vmin,
		vmax=vmax,
	)

	# ax_heat.set_title(title, fontsize=14, pad=10)
	# ax_heat.set_ylabel("Firmware", fontsize=11)
	ax_heat.set_yticks(np.arange(row_count))
	ax_heat.set_yticklabels(firmwares, fontsize=10)
	ax_heat.set_xticks(np.arange(col_count))
	ax_heat.set_xticklabels(_column_labels(columns), rotation=60, ha="right", fontsize=10)

	ax_heat.set_xticks(np.arange(-0.5, col_count, 1), minor=True)
	ax_heat.set_yticks(np.arange(-0.5, row_count, 1), minor=True)
	ax_heat.grid(which="minor", color="white", linewidth=0.45, alpha=0.55)
	ax_heat.tick_params(which="minor", bottom=False, left=False)

	colorbar = fig.colorbar(image, ax=ax_heat, fraction=0.02, pad=0.01)
	# colorbar.set_label(colorbar_label, fontsize=10)

	# Lower panel highlights universality vs concentration by showing across-firmware spread.
	column_std = np.nanstd(matrix, axis=0)
	x_positions = np.arange(col_count)
	ax_spread.bar(x_positions, column_std, color="#4e79a7", alpha=0.85, width=0.82)
	ax_spread.set_ylabel("Std Dev\nacross FW", fontsize=10)
	ax_spread.set_xlabel("Corruption Instance (mode + severity)", fontsize=10)
	ax_spread.grid(axis="y", color="#e0e0e0", linewidth=0.7, alpha=0.9)
	ax_spread.set_axisbelow(True)

	median_std = float(np.nanmedian(column_std))
	ax_spread.axhline(median_std, color="#6d6d6d", linestyle="--", linewidth=1.0)
	ax_spread.text(
		0.995,
		median_std,
		f" median std={median_std:.2f}",
		transform=ax_spread.get_yaxis_transform(),
		ha="right",
		va="bottom",
		fontsize=10,
		color="#5b5b5b",
	)

	for label in ax_spread.get_xticklabels():
		label.set_visible(False)

	fig.savefig(output_path.with_suffix(".svg"))
	fig.savefig(output_path.with_suffix(".pdf"))
	plt.close(fig)


def main():
	parser = argparse.ArgumentParser(
		description=(
			"Generate per-firmware dynamic coverage-ratio heatmap to show universal vs concentrated trends."
		)
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
		"--metric",
		default="coverage_ratio",
		help="Dynamic metric column to visualize (default: %(default)s).",
	)
	parser.add_argument(
		"--include-baseline",
		action="store_true",
		help="Include severity 0 baseline columns (excluded by default).",
	)
	parser.add_argument(
		"--title",
		default=None,
		help="Figure title (default: metric-specific title).",
	)
	args = parser.parse_args()

	logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
	args.output_dir.mkdir(parents=True, exist_ok=True)

	rows = _load_rows(args.dynamic_csv)
	firmwares, columns, matrix, missing_mask = _build_matrix(
		rows,
		args.metric,
		args.include_baseline,
	)

	if matrix.size == 0:
		raise ValueError(
			f"No usable rows for metric '{args.metric}' in {args.dynamic_csv} with current filters."
		)

	metric_config = METRIC_CONFIG.get(args.metric, {})
	output_stem = metric_config.get("output_stem", f"dynamic_{args.metric}_per_firmware_heatmap")
	colorbar_label = metric_config.get("colorbar", f"{args.metric.replace('_', ' ').title()} (%)")
	title = args.title or metric_config.get("title", f"Per-Firmware Heatmap of {args.metric.replace('_', ' ').title()}")

	output_path = args.output_dir / output_stem
	_draw_heatmap(firmwares, columns, matrix, missing_mask, output_path, title, colorbar_label)

	logger.info("Saved figure to %s", output_path.with_suffix(".svg"))
	logger.info("Saved figure to %s", output_path.with_suffix(".pdf"))


if __name__ == "__main__":
	main()
