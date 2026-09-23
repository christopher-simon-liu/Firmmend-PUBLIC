import argparse
import csv
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np


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

METRIC_CONFIG = {
	"coverage_ratio": {
		"title": "Dynamic Analysis Coverage Distribution by Corruption Mode",
		"y_label": "Coverage Ratio (%)",
		"stem": "dynamic_coverage_ratio",
	},
	"crash_ratio": {
		"title": "Dynamic Analysis Crash Ratio Distribution by Corruption Mode",
		"y_label": "Crash Ratio (%)",
		"stem": "dynamic_crash_ratio",
	},
}


def _to_float(value):
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _load_csv_rows(csv_path):
	rows = []
	with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
		reader = csv.DictReader(csv_file)
		for row in reader:
			rows.append(row)
	return rows


def _is_unit_ratio(values):
	if not values:
		return True
	return max(values) <= 2.5


def _mode_sort_key(mode):
	return (MODE_ORDER.get(mode, 99), mode)


def _display_mode_name(mode):
	return mode.replace("_", " ")


def _dot_color_for_mode(mode):
	base = MODE_COLORS.get(mode, "#5c5c5c")
	rgb = np.asarray(mcolors.to_rgb(base))
	darker = np.clip(rgb * 0.62, 0.0, 1.0)
	return darker


def _extract_mode_series(rows, metric):
	grouped = {}
	for row in rows:
		mode = row.get("mode", "").strip()
		if not mode:
			continue
		value = _to_float(row.get(metric))
		if value is None:
			continue
		grouped.setdefault(mode, []).append(value)

	modes = sorted(grouped.keys(), key=_mode_sort_key)
	mode_values = [grouped[mode] for mode in modes]
	return modes, mode_values


def _convert_to_percent(mode_values):
	flat_values = [item for mode_list in mode_values for item in mode_list]
	if _is_unit_ratio(flat_values):
		return [[value * 100.0 for value in mode_list] for mode_list in mode_values]
	return mode_values


def _compute_y_lims(mode_values):
	y_min = min(min(series) for series in mode_values)
	y_max = max(max(series) for series in mode_values)
	y_padding = max((y_max - y_min) * 0.08, 2.0)
	return y_min - y_padding, y_max + y_padding


def _compute_distribution_stats(values):
	array = np.asarray(values, dtype=float)
	n = len(array)
	mean = float(np.mean(array))
	std = float(np.std(array))
	minimum = float(np.min(array))
	maximum = float(np.max(array))
	q1 = float(np.percentile(array, 25))
	median = float(np.percentile(array, 50))
	q3 = float(np.percentile(array, 75))
	iqr = q3 - q1
	lower_fence = q1 - (1.5 * iqr)
	upper_fence = q3 + (1.5 * iqr)
	outlier_count = int(np.sum((array < lower_fence) | (array > upper_fence)))
	outlier_percent = (float(outlier_count) / float(n)) * 100.0 if n else 0.0
	return {
		"mean": mean,
		"std": std,
		"min": minimum,
		"max": maximum,
		"median": median,
		"q1": q1,
		"q3": q3,
		"iqr": iqr,
		"outlier_percent": outlier_percent,
	}


def _write_stats_csv(modes, mode_values, output_path):
	with output_path.open("w", newline="", encoding="utf-8") as csv_file:
		writer = csv.DictWriter(
			csv_file,
			fieldnames=[
				"mode",
				"n",
				"mean",
				"std",
				"min",
				"max",
				"median",
				"q1",
				"q3",
				"iqr",
				"outlier_percent",
			],
		)
		writer.writeheader()
		for mode, values in zip(modes, mode_values):
			stats = _compute_distribution_stats(values)
			writer.writerow(
				{
					"mode": mode,
					"n": len(values),
					"mean": f"{stats['mean']:.6f}",
					"std": f"{stats['std']:.6f}",
					"min": f"{stats['min']:.6f}",
					"max": f"{stats['max']:.6f}",
					"median": f"{stats['median']:.6f}",
					"q1": f"{stats['q1']:.6f}",
					"q3": f"{stats['q3']:.6f}",
					"iqr": f"{stats['iqr']:.6f}",
					"outlier_percent": f"{stats['outlier_percent']:.6f}",
				}
			)


def _style_common_axes(ax, modes, positions, mode_values, title, y_label):
	ax.axhline(100.0, color="#8c8c8c", linestyle="--", linewidth=1.1, alpha=0.8, zorder=0)
	ax.text(
		0.995,
		100.0,
		" baseline (100%)",
		transform=ax.get_yaxis_transform(),
		ha="right",
		va="bottom",
		fontsize=20,
		color="#6f6f6f",
	)

	# ax.set_title(title, fontsize=14, pad=12)
	ax.set_xlabel("Corruption Mode", fontsize=20)
	ax.set_ylabel(y_label, fontsize=20)
	ax.set_xticks(positions)
	ax.set_xticklabels([_display_mode_name(mode) for mode in modes], rotation=15, ha="right", fontsize=20)
	ax.tick_params(axis="y", labelsize=11)
	ax.grid(axis="y", color="#e0e0e0", linestyle="-", linewidth=0.8, alpha=0.9)

	y_low, y_high = _compute_y_lims(mode_values)
	ax.set_ylim(y_low, y_high)

	for idx, values in enumerate(mode_values, start=1):
		ax.text(
			idx,
			0.01,
			f"n={len(values)}",
			transform=ax.get_xaxis_transform(),
			ha="center",
			va="bottom",
			fontsize=20,
			color="#666666",
		)


def _scatter_points(ax, modes, mode_values, alpha=0.55, jitter_span=0.14, clip_paths=None):
	rng = np.random.default_rng(20260624)
	for idx, (mode, values) in enumerate(zip(modes, mode_values), start=1):
		x_jitter = rng.uniform(-jitter_span, jitter_span, len(values))
		scatter = ax.scatter(
			np.full(len(values), idx) + x_jitter,
			values,
			s=20,
			alpha=alpha,
			color=_dot_color_for_mode(mode),
			edgecolors="white",
			linewidths=0.4,
			zorder=3,
		)
		if clip_paths is not None and (idx - 1) < len(clip_paths):
			clip_artist = clip_paths[idx - 1]
			clip_path = clip_artist.get_paths()[0]
			scatter.set_clip_path(clip_path, clip_artist.get_transform())


def _save_figure(fig, output_path):
	fig.tight_layout()
	fig.savefig(output_path.with_suffix(".svg"))
	fig.savefig(output_path.with_suffix(".pdf"))
	plt.close(fig)


def _draw_boxplot(modes, mode_values, output_path, title, y_label):
	positions = np.arange(1, len(modes) + 1)

	fig, ax = plt.subplots(figsize=(10.0, 5.8), dpi=160)

	boxplot = ax.boxplot(
		mode_values,
		positions=positions,
		widths=0.62,
		patch_artist=True,
		showmeans=True,
		meanprops={
			"marker": "D",
			"markerfacecolor": "#111111",
			"markeredgecolor": "white",
			"markersize": 5,
		},
		medianprops={"color": "#111111", "linewidth": 1.8},
		whiskerprops={"color": "#666666", "linewidth": 1.2},
		capprops={"color": "#666666", "linewidth": 1.2},
		flierprops={
			"marker": "o",
			"markerfacecolor": "#444444",
			"markeredgecolor": "white",
			"markersize": 4,
			"alpha": 0.8,
		},
	)

	for box_patch, mode in zip(boxplot["boxes"], modes):
		box_patch.set_facecolor(MODE_COLORS.get(mode, "#9c9c9c"))
		box_patch.set_alpha(0.55)
		box_patch.set_edgecolor("#444444")
		box_patch.set_linewidth(1.2)

	_scatter_points(ax, modes, mode_values, alpha=0.78, jitter_span=0.17)
	_style_common_axes(ax, modes, positions, mode_values, title, y_label)
	_save_figure(fig, output_path)


def _draw_violin_box_overlay(modes, mode_values, output_path, title, y_label):
	positions = np.arange(1, len(modes) + 1)

	fig, ax = plt.subplots(figsize=(10.0, 5.8), dpi=160)

	violin = ax.violinplot(
		mode_values,
		positions=positions,
		widths=0.78,
		showmeans=False,
		showmedians=False,
		showextrema=False,
	)

	for body, mode in zip(violin["bodies"], modes):
		body.set_facecolor(MODE_COLORS.get(mode, "#9c9c9c"))
		body.set_edgecolor("#3a3a3a")
		body.set_linewidth(0.9)
		body.set_alpha(0.38)

	ax.boxplot(
		mode_values,
		positions=positions,
		widths=0.26,
		patch_artist=True,
		showmeans=True,
		meanprops={
			"marker": "D",
			"markerfacecolor": "#111111",
			"markeredgecolor": "white",
			"markersize": 5,
		},
		medianprops={"color": "#111111", "linewidth": 1.8},
		whiskerprops={"color": "#555555", "linewidth": 1.1},
		capprops={"color": "#555555", "linewidth": 1.1},
		flierprops={
			"marker": "o",
			"markerfacecolor": "#3d3d3d",
			"markeredgecolor": "white",
			"markersize": 3,
			"alpha": 0.7,
		},
		boxprops={"facecolor": "#ffffff", "alpha": 0.72, "edgecolor": "#444444", "linewidth": 1.0},
	)

	_scatter_points(
		ax,
		modes,
		mode_values,
		alpha=0.92,
		jitter_span=0.38,
		clip_paths=violin["bodies"],
	)
	_style_common_axes(ax, modes, positions, mode_values, title, y_label)
	_save_figure(fig, output_path)


def main():
	parser = argparse.ArgumentParser(
		description=(
			"Generate dynamic-analysis ratio distribution boxplots by corruption mode."
		)
	)
	parser.add_argument(
		"aggregate_csv",
		type=Path,
		help="Path to dynamic aggregate CSV (for example: results/dynamic_results.csv).",
	)
	parser.add_argument(
		"output_dir",
		type=Path,
		help="Directory where figures will be written.",
	)
	parser.add_argument(
		"--metric",
		default="coverage_ratio",
		help="Metric column to plot (default: %(default)s).",
	)
	parser.add_argument(
		"--title",
		default=None,
		help="Figure title (default: metric-specific title).",
	)
	parser.add_argument(
		"--plot-types",
		nargs="+",
		choices=["box", "violin_box"],
		default=["box", "violin_box"],
		help="Plot variants to render (default: both).",
	)
	args = parser.parse_args()

	logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
	args.output_dir.mkdir(parents=True, exist_ok=True)

	rows = _load_csv_rows(args.aggregate_csv)
	modes, mode_values = _extract_mode_series(rows, args.metric)

	if not modes:
		raise ValueError(
			f"No valid data found for metric '{args.metric}' in CSV: {args.aggregate_csv}"
		)

	percent_values = _convert_to_percent(mode_values)
	metric_cfg = METRIC_CONFIG.get(args.metric, {})
	metric_stem = metric_cfg.get("stem", f"dynamic_{args.metric}")
	y_label = metric_cfg.get("y_label", f"{args.metric.replace('_', ' ').title()} (%)")
	title = args.title or metric_cfg.get(
		"title",
		f"Dynamic Analysis {args.metric.replace('_', ' ').title()} Distribution by Corruption Mode",
	)

	stats_csv_path = args.output_dir / f"{metric_stem}_distribution_stats.csv"
	_write_stats_csv(modes, percent_values, stats_csv_path)
	logger.info("Saved stats CSV to %s", stats_csv_path)

	if "box" in args.plot_types:
		boxplot_path = args.output_dir / f"{metric_stem}_boxplot"
		_draw_boxplot(modes, percent_values, boxplot_path, title, y_label)
		logger.info("Saved figure to %s", boxplot_path.with_suffix(".svg"))
		logger.info("Saved figure to %s", boxplot_path.with_suffix(".pdf"))

	if "violin_box" in args.plot_types:
		violin_title = f"{title} (Violin + Box)"
		violin_path = args.output_dir / f"{metric_stem}_violin_boxplot"
		_draw_violin_box_overlay(modes, percent_values, violin_path, violin_title, y_label)
		logger.info("Saved figure to %s", violin_path.with_suffix(".svg"))
		logger.info("Saved figure to %s", violin_path.with_suffix(".pdf"))


if __name__ == "__main__":
	main()
