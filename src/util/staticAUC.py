#!/usr/bin/env python3

import argparse
import csv
import importlib
import logging
import re
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

MODE_ORDER = {
	"bit_flip": 0,
	"partial_dump": 1,
	"partial_write": 2,
	"partial_erase": 3,
	"address_bit_freeze": 4,
}
DEFAULT_PDF_WIDTH_IN = 7.25
BASE_TEXT_SCALE = 1.8
DEFAULT_TEXT_SCALE = 3.6
REQUIRED_COLUMNS = {
	"mode",
	"tool",
	"metric",
	"repair_auc",
	"no_repair_auc_ratio_to_oracle_donor",
	"repair_auc_ratio_to_oracle_donor",
}


def _safe_filename(text):
	safe = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
	return safe or "figure"


def _display_name(text):
	return text.replace("_", " ").replace("-", " ").title()


def _to_float(value):
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _load_method(csv_path):
	with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
		reader = csv.DictReader(csv_file)
		columns = set(reader.fieldnames or ())
		missing = REQUIRED_COLUMNS - columns
		if missing:
			raise ValueError(f"{csv_path} is missing required columns: {', '.join(sorted(missing))}")
		rows = []
		for row in reader:
			ratio = _to_float(row.get("repair_auc_ratio_to_oracle_donor"))
			no_repair_ratio = _to_float(row.get("no_repair_auc_ratio_to_oracle_donor"))
			auc = _to_float(row.get("repair_auc"))
			if ratio is not None and no_repair_ratio is not None and auc is not None:
				rows.append(
					row
					| {
						"repair_auc": auc,
						"no_repair_auc_ratio_to_oracle_donor": no_repair_ratio,
						"repair_auc_ratio_to_oracle_donor": ratio,
					}
				)
	if not rows:
		raise ValueError(f"{csv_path} has no usable AUC rows")
	return rows


def _write_pdf(figure, svg_path):
	# Let matplotlib's own PDF backend write the file so font metrics match the
	# SVG exactly; round-tripping through cairosvg/Inkscape can substitute fonts
	# with different glyph widths and crowd or overlap text.
	pdf_path = svg_path.with_suffix(".pdf")
	figure.savefig(pdf_path, format="pdf", bbox_inches="tight", pad_inches=0.25)
	logger.info("Saved figure to %s", pdf_path)



TOOL_HATCHES = {"angr": "", "ghidra": "////"}
BACK_BAR_ALPHA = 0.55
FRONT_BAR_LINEWIDTH = 1.3
LEGEND_ROW_HEIGHT_IN = 0.38
LEGEND_TOP_GAP_IN = 1.1
NO_REPAIR_COLOR = "#555555"


def _plot_metric(metric, method_rows, output_dir, pdf_width_in, pdf_height_in, text_scale):
	plt = importlib.import_module("matplotlib.pyplot")
	tools = sorted({row["tool"] for rows in method_rows.values() for row in rows if row["metric"] == metric})
	modes = sorted(
		{row["mode"] for rows in method_rows.values() for row in rows if row["metric"] == metric},
		key=lambda mode: (MODE_ORDER.get(mode, 99), mode),
	)
	if not modes or not tools:
		return

	values = defaultdict(lambda: defaultdict(dict))
	no_repair_values = defaultdict(dict)
	for label, rows in method_rows.items():
		for row in rows:
			if row["metric"] == metric:
				no_repair_values[row["tool"]][row["mode"]] = row["no_repair_auc_ratio_to_oracle_donor"]
				values[row["tool"]][row["mode"]][label] = row["repair_auc_ratio_to_oracle_donor"]

	labels = list(method_rows)
	base_height = pdf_height_in or 5.0
	figure, axis = plt.subplots(figsize=(pdf_width_in, base_height))
	positions = list(range(len(modes)))
	group_width = 0.8
	bar_width = group_width / max(len(labels), 1)
	palette = plt.get_cmap("tab10")

	# Draw the first tool as solid, semi-transparent bars, and overlay every
	# additional tool as a hollow, hatched outline in the same method color so
	# both tools stay legible even where their bars fully overlap.
	for tool_index, tool in enumerate(tools):
		is_back_layer = tool_index == 0
		hatch = TOOL_HATCHES.get(tool, "") if not is_back_layer else ""
		for index, label in enumerate(labels):
			offsets = [position - group_width / 2 + bar_width * (index + 0.5) for position in positions]
			heights = [values[tool][mode].get(label, float("nan")) for mode in modes]
			color = palette(index)
			if is_back_layer:
				axis.bar(offsets, heights, bar_width, facecolor=color, alpha=BACK_BAR_ALPHA, edgecolor="#333333", linewidth=0.4, zorder=2)
			else:
				axis.bar(
					offsets,
					heights,
					bar_width,
					facecolor="none",
					hatch=hatch,
					edgecolor=color,
					linewidth=FRONT_BAR_LINEWIDTH,
					zorder=3,
				)
		for position, mode in zip(positions, modes):
			no_repair_value = no_repair_values[tool].get(mode)
			if no_repair_value is None:
				continue
			if is_back_layer:
				axis.hlines(no_repair_value, position - group_width / 2, position + group_width / 2, colors=NO_REPAIR_COLOR, linewidth=1.8, zorder=4)
			else:
				axis.hlines(
					no_repair_value,
					position - group_width / 2,
					position + group_width / 2,
					colors=NO_REPAIR_COLOR,
					linestyles="--",
					linewidth=1.8,
					zorder=5,
				)

	method_handles = [
		plt.Rectangle((0, 0), 1, 1, facecolor=palette(index), alpha=BACK_BAR_ALPHA, edgecolor="#333333", linewidth=0.4)
		for index in range(len(labels))
	]
	tool_handles = [
		plt.Rectangle((0, 0), 1, 1, facecolor="none", hatch=TOOL_HATCHES.get(tool, ""), edgecolor="#333333", linewidth=FRONT_BAR_LINEWIDTH if index else 0.4)
		for index, tool in enumerate(tools)
	]
	no_repair_handle = plt.Line2D([0], [0], color=NO_REPAIR_COLOR, linewidth=1.8)

	font_scale = text_scale / BASE_TEXT_SCALE
	tick_fontsize = 8 * font_scale
	axis.set_xticks(positions, [_display_name(mode) for mode in modes], rotation=20, ha="right", rotation_mode="anchor", fontsize=tick_fontsize)
	axis.set_ylabel("Functionality AUC", fontsize=9 * font_scale)
	axis.set_title(metric, fontsize=9 * font_scale)
	axis.set_ylim(bottom=0, top=max(1.05, axis.get_ylim()[1] * 1.05))
	axis.grid(axis="y", color="#d9d9d9", linewidth=0.7)
	axis.set_axisbelow(True)

	legend_fontsize = 7 * font_scale
	method_ncols = min(len(labels), 4) if labels else 1
	method_rows_count = -(-len(labels) // method_ncols)
	method_legend = axis.legend(
		method_handles,
		labels,
		frameon=False,
		ncols=method_ncols,
		fontsize=legend_fontsize,
		loc="upper center",
		bbox_to_anchor=(0.5, -LEGEND_TOP_GAP_IN / base_height),
	)
	axis.add_artist(method_legend)
	method_block_in = LEGEND_TOP_GAP_IN + method_rows_count * LEGEND_ROW_HEIGHT_IN + 0.25
	axis.legend(
		tool_handles + [no_repair_handle],
		[_display_name(tool) for tool in tools] + ["No repair"],
		frameon=False,
		ncols=len(tools) + 1,
		fontsize=legend_fontsize,
		loc="upper center",
		bbox_to_anchor=(0.5, -method_block_in / base_height),
	)

	basename = f"repair_auc_ratio_{_safe_filename(metric)}"
	svg_path = output_dir / f"{basename}.svg"
	figure.savefig(svg_path, format="svg", bbox_inches="tight", pad_inches=0.25)
	logger.info("Saved figure to %s", svg_path)
	_write_pdf(figure, svg_path)
	plt.close(figure)


def main():
	parser = argparse.ArgumentParser(description="Compare repair AUC performance from multiple static_results_auc_compare.csv files.")
	parser.add_argument("output_dir", type=Path, help="Directory where AUC comparison figures are saved.")
	parser.add_argument("repair_auc_csv", type=Path, nargs="+", help="One AUC comparison CSV per repair method.")
	parser.add_argument("--labels", nargs="+", help="Labels for the input CSVs, in the same order.")
	parser.add_argument("--pdf-width-in", type=float, default=DEFAULT_PDF_WIDTH_IN, help="Target PDF width in inches (default: %(default)s).")
	parser.add_argument("--pdf-height-in", type=float, default=None, help="Target PDF height in inches (default: preserve figure height).")
	parser.add_argument("--text-scale", type=float, default=DEFAULT_TEXT_SCALE, help="Scale factor for figure text (default: %(default)s).")
	args = parser.parse_args()

	if args.labels and len(args.labels) != len(args.repair_auc_csv):
		parser.error("--labels must provide exactly one label for each repair_auc_csv")
	labels = args.labels or [_display_name(path.parent.parent.name) for path in args.repair_auc_csv]
	if len(set(labels)) != len(labels):
		parser.error("repair method labels must be unique; use --labels to disambiguate them")

	method_rows = dict(zip(labels, (_load_method(path) for path in args.repair_auc_csv)))
	metrics = sorted({row["metric"] for rows in method_rows.values() for row in rows})
	args.output_dir.mkdir(parents=True, exist_ok=True)
	for metric in metrics:
		_plot_metric(metric, method_rows, args.output_dir, args.pdf_width_in, args.pdf_height_in, args.text_scale)


if __name__ == "__main__":
	main()
