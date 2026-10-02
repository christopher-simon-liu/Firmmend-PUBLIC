import argparse
import csv
import importlib
import logging
import re
import subprocess
from html import escape
from pathlib import Path

logger = logging.getLogger(__name__)

METRIC_PAIRS = [
    ("BasicBlock Retention", "ghidra_basicblock_retention", "angr_basicblock_retention"),
    ("BasicBlock Ratio", "ghidra_basicblock_ratio", "angr_basicblock_ratio"),
    ("Function Retention", "ghidra_function_retention", "angr_function_retention"),
    ("Function Ratio", "ghidra_function_ratio", "angr_function_ratio"),
]

TOOL_COLORS = {
    "ghidra": "#1f77b4",
    "angr": "#d62728",
}

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


def _load_aggregate_data(aggregate_csv):
    aggregate_data = []
    with aggregate_csv.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            aggregate_data.append(row)
    return aggregate_data


def _group_by_mode(rows):
    grouped = {}
    for row in rows:
        mode = row.get("mode", "")
        grouped.setdefault(mode, []).append(row)
    return grouped


def _sorted_modes(grouped):
    return sorted(grouped.keys(), key=lambda mode: (MODE_ORDER.get(mode, 99), mode))


def _safe_filename(text):
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return safe or "figure"


def _title_case_filename(text):
    title_text = text.replace("_", " ").replace("-", " ").title()
    return _safe_filename(title_text)


def _svg_text(x, y, text, size=18, anchor="start", fill="#202020", weight="normal", text_scale=1.0):
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-family="Arial, sans-serif" '
        f'font-size="{size * text_scale:.2f}" text-anchor="{anchor}" fill="{fill}" '
        f'font-weight="{weight}">{escape(text)}</text>'
    )


def _format_tick(value):
    return f"{value:.2f}"


def _metric_points(rows, metric):
    points = []
    for row in rows:
        severity = _to_float(row.get("severity"))
        value = _to_float(row.get(metric))
        if severity is None or value is None:
            continue
        points.append((severity, value))
    points.sort(key=lambda item: item[0])
    return points


def _draw_subplot(rows, title, ghidra_metric, angr_metric, box, text_scale):
    left, top, right, bottom = box
    title_height = 54
    plot_left = left + 118
    plot_top = top + title_height + 24
    plot_right = right - 54
    plot_bottom = bottom - 140
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    ghidra_points = _metric_points(rows, ghidra_metric)
    angr_points = _metric_points(rows, angr_metric)
    all_points = ghidra_points + angr_points

    parts = [
        f'<rect x="{left}" y="{top}" width="{right - left}" height="{bottom - top}" '
        'fill="#ffffff" stroke="#d0d0d0" stroke-width="2" />',
        _svg_text(left + 8, top + 22, title, size=24, weight="bold", text_scale=text_scale),
    ]

    if not all_points:
        parts.append(
            _svg_text(
                (left + right) / 2,
                (top + bottom) / 2,
                "No data",
                size=20,
                anchor="middle",
                fill="#777777",
                text_scale=text_scale,
            )
        )
        return "\n".join(parts)

    severities = [item[0] for item in all_points]
    values = [item[1] for item in all_points]

    min_x = min(severities)
    max_x = max(severities)
    min_y = min(values)
    max_y = max(values)

    if min_x == max_x:
        pad = 0.5 if min_x == 0 else abs(min_x) * 0.1
        min_x -= pad
        max_x += pad
    if min_y == max_y:
        pad = 0.5 if min_y == 0 else abs(min_y) * 0.1
        min_y -= pad
        max_y += pad

    def map_x(value):
        return plot_left + (value - min_x) / (max_x - min_x) * plot_width

    def map_y(value):
        return plot_bottom - (value - min_y) / (max_y - min_y) * plot_height

    grid_color = "#ededed"
    axis_color = "#666666"

    for tick_index in range(5):
        frac = tick_index / 4
        x = plot_left + frac * plot_width
        y = plot_bottom - frac * plot_height
        parts.append(
            f'<line x1="{x:.2f}" y1="{plot_top:.2f}" x2="{x:.2f}" y2="{plot_bottom:.2f}" stroke="{grid_color}" stroke-width="1" />'
        )
        parts.append(
            f'<line x1="{plot_left:.2f}" y1="{y:.2f}" x2="{plot_right:.2f}" y2="{y:.2f}" stroke="{grid_color}" stroke-width="1" />'
        )

    parts.append(
        f'<line x1="{plot_left:.2f}" y1="{plot_top:.2f}" x2="{plot_left:.2f}" y2="{plot_bottom:.2f}" stroke="{axis_color}" stroke-width="2" />'
    )
    parts.append(
        f'<line x1="{plot_left:.2f}" y1="{plot_bottom:.2f}" x2="{plot_right:.2f}" y2="{plot_bottom:.2f}" stroke="{axis_color}" stroke-width="2" />'
    )

    def _add_series(series_points, color):
        if len(series_points) > 1:
            polyline_points = " ".join(
                f"{map_x(severity):.2f},{map_y(value):.2f}" for severity, value in series_points
            )
            parts.append(
                f'<polyline points="{polyline_points}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" />'
            )

        for severity, value in series_points:
            x = map_x(severity)
            y = map_y(value)
            parts.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}" stroke="#ffffff" stroke-width="1" />'
            )

    _add_series(ghidra_points, TOOL_COLORS["ghidra"])
    _add_series(angr_points, TOOL_COLORS["angr"])

    legend_x = plot_right - 320
    legend_y = plot_top + 24
    legend_row_gap = max(42.0, 30.0 * text_scale)
    for idx, (label, color) in enumerate((("ghidra", TOOL_COLORS["ghidra"]), ("angr", TOOL_COLORS["angr"]))):
        y = legend_y + idx * legend_row_gap
        parts.append(
            f'<line x1="{legend_x:.2f}" y1="{y:.2f}" x2="{legend_x + 28:.2f}" y2="{y:.2f}" stroke="{color}" stroke-width="3" />'
        )
        parts.append(_svg_text(legend_x + 40, y + 8, label, size=18, fill="#555555", text_scale=text_scale))

    tick_values = [min_x, min_x + (max_x - min_x) / 2, max_x]
    for value in tick_values:
        x = map_x(value)
        label = _format_tick(value)
        parts.append(_svg_text(x, plot_bottom + 56, label, size=22, anchor="middle", fill="#666666", text_scale=text_scale))

    y_tick_values = [min_y, min_y + (max_y - min_y) / 2, max_y]
    for value in y_tick_values:
        y = map_y(value)
        label = _format_tick(value)
        parts.append(_svg_text(plot_left - 22, y + 6, label, size=22, anchor="end", fill="#666666", text_scale=text_scale))

    parts.append(
        _svg_text(
            (plot_left + plot_right) / 2,
            bottom - 30,
            "Severity",
            size=22,
            anchor="middle",
            fill="#666666",
            text_scale=text_scale,
        )
    )
    return "\n".join(parts)


def _plot_mode_png(mode, rows, output_dir, text_scale):
    try:
        image_mod = importlib.import_module("PIL.Image")
        image_draw_mod = importlib.import_module("PIL.ImageDraw")
        image_font_mod = importlib.import_module("PIL.ImageFont")
    except ImportError:
        logger.warning("Pillow is not installed. Skipping PNG output for mode: %s", mode)
        return None

    Image = image_mod
    ImageDraw = image_draw_mod
    ImageFont = image_font_mod

    width = 2600
    height = 1650
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    font_size_title = max(14, int(round(16 * text_scale)))
    font_size_tick = max(12, int(round(14 * text_scale)))
    font_size_axis = max(12, int(round(15 * text_scale)))
    font_size_legend = max(12, int(round(13 * text_scale)))

    try:
        font_title = ImageFont.truetype("DejaVuSans.ttf", font_size_title)
        font_tick = ImageFont.truetype("DejaVuSans.ttf", font_size_tick)
        font_axis = ImageFont.truetype("DejaVuSans.ttf", font_size_axis)
        font_legend = ImageFont.truetype("DejaVuSans.ttf", font_size_legend)
    except OSError:
        font_title = ImageFont.load_default()
        font_tick = ImageFont.load_default()
        font_axis = ImageFont.load_default()
        font_legend = ImageFont.load_default()

    left_margin = 70
    right_margin = 70
    top_margin = 120
    bottom_margin = 70
    h_gap = 70
    v_gap = 70

    cols = 2
    rows_count = 2
    subplot_width = (width - left_margin - right_margin - (cols - 1) * h_gap) / cols
    subplot_height = (height - top_margin - bottom_margin - (rows_count - 1) * v_gap) / rows_count

    for index, (title, ghidra_metric, angr_metric) in enumerate(METRIC_PAIRS):
        row_index = index // cols
        col_index = index % cols
        left = left_margin + col_index * (subplot_width + h_gap)
        top = top_margin + row_index * (subplot_height + v_gap)
        right = left + subplot_width
        bottom = top + subplot_height

        draw.rectangle((left, top, right, bottom), outline=(208, 208, 208), width=2)
        draw.text((left + 8, top + 8), title, fill=(32, 32, 32), font=font_title)

        plot_left = left + 118
        plot_top = top + 78
        plot_right = right - 54
        plot_bottom = bottom - 132
        plot_width = plot_right - plot_left
        plot_height = plot_bottom - plot_top

        ghidra_points = _metric_points(rows, ghidra_metric)
        angr_points = _metric_points(rows, angr_metric)
        all_points = ghidra_points + angr_points

        if not all_points:
            draw.text(((left + right) / 2 - 24, (top + bottom) / 2), "No data", fill=(120, 120, 120), font=font_title)
            continue

        severities = [item[0] for item in all_points]
        values = [item[1] for item in all_points]

        min_x = min(severities)
        max_x = max(severities)
        min_y = min(values)
        max_y = max(values)

        if min_x == max_x:
            pad = 0.5 if min_x == 0 else abs(min_x) * 0.1
            min_x -= pad
            max_x += pad
        if min_y == max_y:
            pad = 0.5 if min_y == 0 else abs(min_y) * 0.1
            min_y -= pad
            max_y += pad

        def map_x(value):
            return plot_left + (value - min_x) / (max_x - min_x) * plot_width

        def map_y(value):
            return plot_bottom - (value - min_y) / (max_y - min_y) * plot_height

        for tick_index in range(5):
            frac = tick_index / 4
            x = plot_left + frac * plot_width
            y = plot_bottom - frac * plot_height
            draw.line((x, plot_top, x, plot_bottom), fill=(237, 237, 237), width=1)
            draw.line((plot_left, y, plot_right, y), fill=(237, 237, 237), width=1)

        draw.line((plot_left, plot_top, plot_left, plot_bottom), fill=(102, 102, 102), width=2)
        draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill=(102, 102, 102), width=2)

        ghidra_color = tuple(int(TOOL_COLORS["ghidra"][i : i + 2], 16) for i in (1, 3, 5))
        angr_color = tuple(int(TOOL_COLORS["angr"][i : i + 2], 16) for i in (1, 3, 5))

        for series_points, color in ((ghidra_points, ghidra_color), (angr_points, angr_color)):
            mapped_points = [(map_x(sev), map_y(val)) for sev, val in series_points]
            if len(mapped_points) > 1:
                draw.line(mapped_points, fill=color, width=3)
            for x, y in mapped_points:
                draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color, outline=(255, 255, 255), width=1)

        tick_values = [min_x, min_x + (max_x - min_x) / 2, max_x]
        for value in tick_values:
            x = map_x(value)
            draw.text((x - 30, plot_bottom + 28), _format_tick(value), fill=(102, 102, 102), font=font_tick)

        y_tick_values = [min_y, min_y + (max_y - min_y) / 2, max_y]
        for value in y_tick_values:
            y = map_y(value)
            draw.text((plot_left - 120, y - 12), _format_tick(value), fill=(102, 102, 102), font=font_tick)

        draw.text(((plot_left + plot_right) / 2 - 48, bottom - 52), "Severity", fill=(102, 102, 102), font=font_axis)

        legend_x = plot_right - 320
        legend_y = plot_top + 24
        legend_row_gap = max(42, int(round(2.2 * font_size_legend)))
        draw.line((legend_x, legend_y, legend_x + 28, legend_y), fill=ghidra_color, width=3)
        draw.text((legend_x + 40, legend_y - 12), "ghidra", fill=(85, 85, 85), font=font_legend)
        draw.line((legend_x, legend_y + legend_row_gap, legend_x + 28, legend_y + legend_row_gap), fill=angr_color, width=3)
        draw.text((legend_x + 40, legend_y + legend_row_gap - 12), "angr", fill=(85, 85, 85), font=font_legend)

    output_path = output_dir / f"{_title_case_filename(mode)}_Severity_Metrics.png"
    image.save(output_path)
    logger.info("Saved figure to %s", output_path)
    return output_path


def _plot_mode_pdf(svg_path, svg_width_px, svg_height_px, pdf_width_in, pdf_height_in):
    pdf_path = svg_path.with_suffix(".pdf")
    if pdf_height_in is None:
        pdf_height_in = pdf_width_in * (svg_height_px / svg_width_px)

    target_width_px = max(1, int(round(pdf_width_in * 96.0)))
    target_height_px = max(1, int(round(pdf_height_in * 96.0)))

    try:
        cairosvg = importlib.import_module("cairosvg")
        cairosvg.svg2pdf(
            url=str(svg_path),
            write_to=str(pdf_path),
            output_width=target_width_px,
            output_height=target_height_px,
        )
        logger.info("Saved figure to %s", pdf_path)
        return
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("CairoSVG conversion failed for %s: %s", svg_path, exc)

    try:
        inkscape_result = subprocess.run(
            [
                "inkscape",
                str(svg_path),
                "--export-type=pdf",
                f"--export-filename={pdf_path}",
                f"--export-width={target_width_px}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if inkscape_result.returncode == 0:
            logger.info("Saved figure to %s", pdf_path)
            return
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.warning("Inkscape conversion failed for %s: %s", svg_path, exc)

    logger.warning(
        "Skipping PDF output for %s: install CairoSVG or Inkscape for vector PDF export.",
        svg_path.name,
    )


def _plot_mode_figure(mode, rows, output_dir, pdf_width_in, pdf_height_in, text_scale, with_png):
    width = 2600
    height = 1650
    left_margin = 70
    right_margin = 70
    top_margin = 120
    bottom_margin = 70
    h_gap = 70
    v_gap = 70

    cols = 2
    rows_count = 2
    subplot_width = (width - left_margin - right_margin - (cols - 1) * h_gap) / cols
    subplot_height = (height - top_margin - bottom_margin - (rows_count - 1) * v_gap) / rows_count

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />',
    ]

    for index, (title, ghidra_metric, angr_metric) in enumerate(METRIC_PAIRS):
        row_index = index // cols
        col_index = index % cols
        left = left_margin + col_index * (subplot_width + h_gap)
        top = top_margin + row_index * (subplot_height + v_gap)
        box = (left, top, left + subplot_width, top + subplot_height)
        parts.append(_draw_subplot(rows, title, ghidra_metric, angr_metric, box, text_scale))

    parts.append("</svg>")

    output_path = output_dir / f"{_title_case_filename(mode)}_Severity_Metrics.svg"
    output_path.write_text("\n".join(parts), encoding="utf-8")
    logger.info("Saved figure to %s", output_path)
    if with_png:
        _plot_mode_png(mode, rows, output_dir, text_scale)
    _plot_mode_pdf(output_path, width, height, pdf_width_in, pdf_height_in)


def main():
    parser = argparse.ArgumentParser(description="Generate figures from aggregated data.")
    parser.add_argument("aggregate_csv", type=Path, help="Path to the aggregate CSV file.")
    parser.add_argument("output_dir", type=Path, help="Directory to save the generated figures.")
    parser.add_argument(
        "--pdf-width-in",
        type=float,
        default=DEFAULT_PDF_WIDTH_IN,
        help="Target PDF width in inches (default: %(default)s, suitable for 2-column LaTeX).",
    )
    parser.add_argument(
        "--pdf-height-in",
        type=float,
        default=None,
        help="Target PDF height in inches (default: preserve aspect ratio).",
    )
    parser.add_argument(
        "--text-scale",
        type=float,
        default=DEFAULT_TEXT_SCALE,
        help="Scale factor for SVG/PDF text labels (default: %(default)s).",
    )
    parser.add_argument(
        "--with-png",
        action="store_true",
        help="Also export PNG files (disabled by default for vector-only output).",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    aggregate_data = _load_aggregate_data(args.aggregate_csv)
    grouped = _group_by_mode(aggregate_data)

    for mode in _sorted_modes(grouped):
        rows = grouped[mode]
        if not mode:
            continue
        _plot_mode_figure(
            mode,
            rows,
            args.output_dir,
            args.pdf_width_in,
            args.pdf_height_in,
            args.text_scale,
            args.with_png,
        )


if __name__ == "__main__":
    main()
