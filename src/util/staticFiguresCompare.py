import argparse
import csv
import importlib
import logging
import re
import subprocess
from html import escape
from pathlib import Path

logger = logging.getLogger(__name__)

METRICS = (
	("BasicBlock Retention", "basicblock_retention"),
	("BasicBlock Ratio", "basicblock_ratio"),
	("Function Retention", "function_retention"),
	("Function Ratio", "function_ratio"),
)

METHOD_COLORS = ("#00ff00", "#ff0000", "#0000FF")
MODE_ORDER = {
	"bit_flip": 0,
	"partial_dump": 1,
	"partial_erase": 2,
	"partial_write": 3,
	"address_bit_freeze": 4,
}
DEFAULT_PDF_WIDTH_IN = 7.0
DEFAULT_TEXT_SCALE = 3.0


def _to_float(value):
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _load_data(csv_path):
	with csv_path.open("r", newline="", encoding="utf-8") as csv_file:
		return list(csv.DictReader(csv_file))


def _group_by_mode(rows):
	grouped = {}
	for row in rows:
		grouped.setdefault(row.get("mode", ""), []).append(row)
	return grouped


def _safe_filename(text):
	safe = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
	return safe or "figure"


def _title_case_filename(text):
	return _safe_filename(text.replace("_", " ").replace("-", " ").title())


def _svg_text(x, y, text, size=18, anchor="start", fill="#202020", weight="normal", text_scale=1.0):
	return (
		f'<text x="{x:.2f}" y="{y:.2f}" font-family="Arial, sans-serif" '
		f'font-size="{size * text_scale:.2f}" text-anchor="{anchor}" fill="{fill}" '
		f'font-weight="{weight}">{escape(text)}</text>'
	)


def _metric_points(rows, metric):
	points = []
	for row in rows:
		severity = _to_float(row.get("severity"))
		value = _to_float(row.get(metric))
		if severity is not None and value is not None:
			points.append((severity, value))
	return sorted(points)


def _area_under_curve(points):
	return sum(
		(next_severity - severity) * (value + next_value) / 2
		for (severity, value), (next_severity, next_value) in zip(points, points[1:])
	)


def _write_auc_csv(grouped_methods, repair_label, modes, output_dir):
	output_path = output_dir / "static_results_auc_compare.csv"
	with output_path.open("w", newline="", encoding="utf-8") as csv_file:
		writer = csv.DictWriter(
			csv_file,
			fieldnames=(
				"mode",
				"tool",
				"metric",
				"oracle_donor_auc",
				"no_repair_auc",
				"repair_auc",
				"no_repair_auc_ratio_to_oracle_donor",
				"repair_auc_ratio_to_oracle_donor",
			),
		)
		writer.writeheader()
		for mode in modes:
			for tool in ("ghidra", "angr"):
				for metric_name, metric_suffix in METRICS:
					metric = f"{tool}_{metric_suffix}"
					aucs = [
						_area_under_curve(_metric_points(grouped.get(mode, []), metric))
						for grouped in grouped_methods
					]
					oracle_auc, no_repair_auc, repair_auc = aucs
					writer.writerow(
						{
							"mode": mode,
							"tool": tool,
							"metric": metric_name,
							"oracle_donor_auc": oracle_auc,
							"no_repair_auc": no_repair_auc,
							"repair_auc": repair_auc,
							"no_repair_auc_ratio_to_oracle_donor": no_repair_auc / oracle_auc if oracle_auc else "",
							"repair_auc_ratio_to_oracle_donor": repair_auc / oracle_auc if oracle_auc else "",
						}
					)
	logger.info("Saved AUC comparison data for %s to %s", repair_label, output_path)


def _axis_range(series):
	values = [value for points in series for _, value in points]
	severities = [severity for points in series for severity, _ in points]
	if not values:
		return None
	min_x, max_x = min(severities), max(severities)
	min_y, max_y = min(values), max(values)
	if min_x == max_x:
		padding = 0.5 if min_x == 0 else abs(min_x) * 0.1
		min_x, max_x = min_x - padding, max_x + padding
	if min_y == max_y:
		padding = 0.5 if min_y == 0 else abs(min_y) * 0.1
		min_y, max_y = min_y - padding, max_y + padding
	return min_x, max_x, min_y, max_y


def _draw_subplot(method_rows, labels, title, metric, box, text_scale):
	left, top, right, bottom = box
	plot_left, plot_top = left + 118, top + 78
	plot_right, plot_bottom = right - 54, bottom - 132
	plot_width, plot_height = plot_right - plot_left, plot_bottom - plot_top
	series = [_metric_points(rows, metric) for rows in method_rows]
	parts = [
		f'<rect x="{left}" y="{top}" width="{right - left}" height="{bottom - top}" fill="#ffffff" stroke="#d0d0d0" stroke-width="2" />',
		_svg_text(left + 8, top + 22, title, size=24, weight="bold", text_scale=text_scale),
	]
	axis_range = _axis_range(series)
	if axis_range is None:
		parts.append(_svg_text((left + right) / 2, (top + bottom) / 2, "No data", size=20, anchor="middle", fill="#777777", text_scale=text_scale))
		return "\n".join(parts)

	min_x, max_x, min_y, max_y = axis_range

	def map_x(value):
		return plot_left + (value - min_x) / (max_x - min_x) * plot_width

	def map_y(value):
		return plot_bottom - (value - min_y) / (max_y - min_y) * plot_height

	for tick_index in range(5):
		fraction = tick_index / 4
		x, y = plot_left + fraction * plot_width, plot_bottom - fraction * plot_height
		parts.append(f'<line x1="{x:.2f}" y1="{plot_top:.2f}" x2="{x:.2f}" y2="{plot_bottom:.2f}" stroke="#ededed" stroke-width="1" />')
		parts.append(f'<line x1="{plot_left:.2f}" y1="{y:.2f}" x2="{plot_right:.2f}" y2="{y:.2f}" stroke="#ededed" stroke-width="1" />')
	parts.append(f'<line x1="{plot_left:.2f}" y1="{plot_top:.2f}" x2="{plot_left:.2f}" y2="{plot_bottom:.2f}" stroke="#666666" stroke-width="2" />')
	parts.append(f'<line x1="{plot_left:.2f}" y1="{plot_bottom:.2f}" x2="{plot_right:.2f}" y2="{plot_bottom:.2f}" stroke="#666666" stroke-width="2" />')

	for points, color in zip(series, METHOD_COLORS[1:]):
		if len(points) > 1:
			polyline = " ".join(f"{map_x(severity):.2f},{map_y(value):.2f}" for severity, value in points)
			parts.append(f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" />')
		for severity, value in points:
			parts.append(f'<circle cx="{map_x(severity):.2f}" cy="{map_y(value):.2f}" r="4" fill="{color}" stroke="#ffffff" stroke-width="1" />')

	legend_x, legend_y = plot_right - 400, plot_top + 24
	for index, (label, color) in enumerate(zip(labels, METHOD_COLORS[1:])):
		y = legend_y + index * max(42.0, 30.0 * text_scale)
		parts.append(f'<line x1="{legend_x:.2f}" y1="{y:.2f}" x2="{legend_x + 28:.2f}" y2="{y:.2f}" stroke="{color}" stroke-width="3" />')
		parts.append(_svg_text(legend_x + 40, y + 8, label, size=18, fill="#555555", text_scale=text_scale))

	for value in (min_x, (min_x + max_x) / 2, max_x):
		parts.append(_svg_text(map_x(value), plot_bottom + 56, f"{value:.2f}", size=22, anchor="middle", fill="#666666", text_scale=text_scale))
	for value in (min_y, (min_y + max_y) / 2, max_y):
		parts.append(_svg_text(plot_left - 22, map_y(value) + 6, f"{value:.2f}", size=22, anchor="end", fill="#666666", text_scale=text_scale))
	parts.append(_svg_text((plot_left + plot_right) / 2, bottom - 30, "Severity", size=22, anchor="middle", fill="#666666", text_scale=text_scale))
	return "\n".join(parts)


def _write_pdf(svg_path, width, height, pdf_width_in, pdf_height_in):
	pdf_path = svg_path.with_suffix(".pdf")
	pdf_height_in = pdf_height_in or pdf_width_in * height / width
	try:
		cairosvg = importlib.import_module("cairosvg")
		cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf_path), output_width=round(pdf_width_in * 96), output_height=round(pdf_height_in * 96))
		logger.info("Saved figure to %s", pdf_path)
		return
	except ImportError:
		pass
	except Exception as exc:
		logger.warning("CairoSVG conversion failed for %s: %s", svg_path, exc)
	try:
		result = subprocess.run(["inkscape", str(svg_path), "--export-type=pdf", f"--export-filename={pdf_path}", f"--export-width={round(pdf_width_in * 96)}"], check=False, capture_output=True, text=True)
		if result.returncode == 0:
			logger.info("Saved figure to %s", pdf_path)
			return
	except FileNotFoundError:
		pass
	logger.warning("Skipping PDF output for %s: install CairoSVG or Inkscape.", svg_path.name)


def _plot_mode(tool, mode, grouped_methods, labels, output_dir, pdf_width_in, pdf_height_in, text_scale):
	width, height = 2600, 1650
	left_margin, right_margin, top_margin, bottom_margin = 70, 70, 120, 70
	horizontal_gap, vertical_gap = 70, 70
	subplot_width = (width - left_margin - right_margin - horizontal_gap) / 2
	subplot_height = (height - top_margin - bottom_margin - vertical_gap) / 2
	parts = [
		'<?xml version="1.0" encoding="UTF-8"?>',
		f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
		f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />',
	]
	method_rows = [grouped.get(mode, []) for grouped in grouped_methods]
	for index, (title, metric_suffix) in enumerate(METRICS):
		row_index, column_index = divmod(index, 2)
		left = left_margin + column_index * (subplot_width + horizontal_gap)
		top = top_margin + row_index * (subplot_height + vertical_gap)
		metric = f"{tool}_{metric_suffix}"
		parts.append(_draw_subplot(method_rows, labels, title, metric, (left, top, left + subplot_width, top + subplot_height), text_scale))
	parts.append("</svg>")
	output_path = output_dir / f"{_title_case_filename(tool)}_{_title_case_filename(mode)}_Severity_Metrics_Compare.svg"
	output_path.write_text("\n".join(parts), encoding="utf-8")
	logger.info("Saved figure to %s", output_path)
	_write_pdf(output_path, width, height, pdf_width_in, pdf_height_in)


def _repair_label(csv_path):
	name = csv_path.parent.name.replace("_", " ").replace("-", " ").strip()
	return name.title() or "Repair"


def main():
	parser = argparse.ArgumentParser(description="Overlay static-analysis metrics for oracle, unrepaired, and repaired firmware.")
	parser.add_argument("oracle_csv", type=Path, help="Aggregate CSV for the oracle_donor method.")
	parser.add_argument("no_repair_csv", type=Path, help="Aggregate CSV for the no_repair method.")
	parser.add_argument("repair_csv", type=Path, help="Aggregate CSV for the repair method to compare.")
	parser.add_argument("output_dir", type=Path, help="Directory to save comparison figures.")
	parser.add_argument("--repair-label", help="Legend label for the repair CSV (default: its parent directory name).")
	parser.add_argument("--pdf-width-in", type=float, default=DEFAULT_PDF_WIDTH_IN, help="Target PDF width in inches (default: %(default)s).")
	parser.add_argument("--pdf-height-in", type=float, default=None, help="Target PDF height in inches (default: preserve aspect ratio).")
	parser.add_argument("--text-scale", type=float, default=DEFAULT_TEXT_SCALE, help="Scale factor for SVG/PDF text labels (default: %(default)s).")
	args = parser.parse_args()

	grouped_methods = [_group_by_mode(_load_data(path)) for path in (args.oracle_csv, args.no_repair_csv, args.repair_csv)]
	labels = ("Oracle Donor", "No Repair", args.repair_label or _repair_label(args.repair_csv))
	modes = sorted(set().union(*(grouped.keys() for grouped in grouped_methods)) - {""}, key=lambda mode: (MODE_ORDER.get(mode, 99), mode))
	args.output_dir.mkdir(parents=True, exist_ok=True)
	_write_auc_csv(grouped_methods, labels[2], modes, args.output_dir)
	plot_methods = grouped_methods[1:]
	plot_labels = labels[1:]
	for mode in modes:
		for tool in ("ghidra", "angr"):
			_plot_mode(tool, mode, plot_methods, plot_labels, args.output_dir, args.pdf_width_in, args.pdf_height_in, args.text_scale)


if __name__ == "__main__":
	main()
