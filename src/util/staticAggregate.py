import argparse
import csv
import json
import os
from pathlib import Path
import logging
import re

logger = logging.getLogger(__name__)

SUMMARY_COLUMNS = [
    "firmware",
    "mode",
    "severity",
    "trial",
    "angr_disassembly_success",
    "angr_num_blocks",
    "angr_num_edges",
    "angr_num_functions",
    "angr_basicblock_retention",
    "angr_basicblock_ratio",
    "angr_function_retention",
    "angr_function_ratio",
    "ghidra_disassembly_success",
    "ghidra_num_blocks",
    "ghidra_num_edges",
    "ghidra_num_functions",
    "ghidra_basicblock_retention",
    "ghidra_basicblock_ratio",
    "ghidra_function_retention",
    "ghidra_function_ratio",
]

AVERAGE_COLUMNS = [
    "firmware",
    "mode",
    "severity",
    "trial_count",
    "angr_disassembly_success",
    "angr_num_blocks",
    "angr_num_edges",
    "angr_num_functions",
    "angr_basicblock_retention",
    "angr_basicblock_ratio",
    "angr_function_retention",
    "angr_function_ratio",
    "ghidra_disassembly_success",
    "ghidra_num_blocks",
    "ghidra_num_edges",
    "ghidra_num_functions",
    "ghidra_basicblock_retention",
    "ghidra_basicblock_ratio",
    "ghidra_function_retention",
    "ghidra_function_ratio",
]

AGGREGATE_COLUMNS = [
    "mode",
    "severity",
    "firmware_count",
    "total_trial_count",
    "angr_disassembly_success",
    "angr_num_blocks",
    "angr_num_edges",
    "angr_num_functions",
    "angr_basicblock_retention",
    "angr_basicblock_ratio",
    "angr_function_retention",
    "angr_function_ratio",
    "ghidra_disassembly_success",
    "ghidra_num_blocks",
    "ghidra_num_edges",
    "ghidra_num_functions",
    "ghidra_basicblock_retention",
    "ghidra_basicblock_ratio",
    "ghidra_function_retention",
    "ghidra_function_ratio",
]

MODE_DISASSEMBLY_COLUMNS = [
    "mode",
    "case_count",
    "angr_case_count",
    "angr_disassembly_success_percent",
    "ghidra_case_count",
    "ghidra_disassembly_success_percent",
]

TRIALS_TO_AVERAGE = {"alpha", "beta", "congroo"}
BASELINE_TRIAL = "baseline"

METRIC_COLUMNS = [
    "angr_disassembly_success",
    "angr_num_blocks",
    "angr_num_edges",
    "angr_num_functions",
    "angr_basicblock_retention",
    "angr_basicblock_ratio",
    "angr_function_retention",
    "angr_function_ratio",
    "ghidra_disassembly_success",
    "ghidra_num_blocks",
    "ghidra_num_edges",
    "ghidra_num_functions",
    "ghidra_basicblock_retention",
    "ghidra_basicblock_ratio",
    "ghidra_function_retention",
    "ghidra_function_ratio",
]

CASE_PATTERN = re.compile(
    r"^(?P<mode>.+)_(?P<severity>[0-9]*\.?[0-9]+(?:[eE][-+]?\d+)?)_(?P<trial>.+)$"
)


def _empty_metrics(prefix):
    return {
        f"{prefix}_disassembly_success": "",
        f"{prefix}_num_blocks": "",
        f"{prefix}_num_edges": "",
        f"{prefix}_num_functions": "",
        f"{prefix}_basicblock_retention": "",
        f"{prefix}_basicblock_ratio": "",
        f"{prefix}_function_retention": "",
        f"{prefix}_function_ratio": "",
    }


def parse_case_metadata(relative_dir, binary_name):
    firmware = ""
    if binary_name:
        # binary_name may be a full workspace path from the tool summary
        # (e.g. "workspace/repairs/.../Drone.bit_flip-0.01.zero_fill.mend.bin"),
        # so reduce it to the bare filename before taking the firmware token.
        firmware = Path(str(binary_name).replace("\\", "/")).name.split(".", 1)[0]

    mode = ""
    severity = ""
    trial = ""

    parts = list(relative_dir.parts)
    for idx in range(len(parts) - 1, -1, -1):
        match = CASE_PATTERN.match(parts[idx])
        if match:
            mode = match.group("mode")
            severity = match.group("severity")
            trial = match.group("trial")
            break

    return firmware, mode, severity, trial


def load_summary(summary_path):
    with summary_path.open("r", encoding="utf-8") as summary_file:
        data = json.load(summary_file)

    return {
        "binary_name": data.get("binary_name", ""),
        "disassembly_success": data.get("disassembly_success", ""),
        "num_blocks": data.get("num_blocks", ""),
        "num_edges": data.get("num_edges", ""),
        "num_functions": data.get("num_functions", ""),
    }


def severity_sort_value(severity):
    if severity == "":
        return (1, 0.0)
    try:
        return (0, float(severity))
    except (TypeError, ValueError):
        return (1, 0.0)


def collect_rows(results_folder):
    rows_by_key = {}
    patterns = (("angr", "*_angr.json"), ("ghidra", "*_ghidra.json"))

    for tool_name, pattern in patterns:
        for summary_path in results_folder.rglob(pattern):
            summary = load_summary(summary_path)
            relative_dir = summary_path.relative_to(results_folder).parent
            relative_key = str(relative_dir)
            binary_name = summary["binary_name"] or summary_path.stem.replace(f"_{tool_name}", "")
            row_key = (relative_key, binary_name)

            if row_key not in rows_by_key:
                firmware, mode, severity, trial = parse_case_metadata(relative_dir, binary_name)
                rows_by_key[row_key] = {
                    "firmware": firmware,
                    "mode": mode,
                    "severity": severity,
                    "trial": trial,
                    **_empty_metrics("angr"),
                    **_empty_metrics("ghidra"),
                }

            rows_by_key[row_key][f"{tool_name}_disassembly_success"] = summary["disassembly_success"]
            rows_by_key[row_key][f"{tool_name}_num_blocks"] = summary["num_blocks"]
            rows_by_key[row_key][f"{tool_name}_num_edges"] = summary["num_edges"]
            rows_by_key[row_key][f"{tool_name}_num_functions"] = summary["num_functions"]

            # Ghidra reports success whenever headless analysis exits cleanly, even
            # when it recovered nothing. Treat "zero blocks" as a failed disassembly
            # so the flag is comparable with angr's.
            if tool_name == "ghidra":
                blocks = _to_float_or_none(summary["num_blocks"])
                if blocks is not None:
                    rows_by_key[row_key]["ghidra_disassembly_success"] = 1 if blocks > 0 else 0

    rows = list(rows_by_key.values())
    rows.sort(
        key=lambda row: (
            row["firmware"],
            row["mode"],
            severity_sort_value(row["severity"]),
            row["trial"],
        )
    )
    return rows


def _to_float_or_none(value):
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int_or_none(value):
    if value in ("", None):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text, 0)
    except (TypeError, ValueError):
        return None


def _format_average(value):
    if value is None:
        return ""
    if value.is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _is_baseline_case(severity, trial):
    return _to_float_or_none(severity) == 0.0 or str(trial).lower() == BASELINE_TRIAL


def _load_function_address_set(functions_csv_path):
    addresses = set()
    try:
        with functions_csv_path.open("r", newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames is None:
                return addresses
            for row in reader:
                addr = _to_int_or_none(row.get("fva"))
                if addr is not None:
                    addresses.add(addr)
    except OSError:
        logger.warning("Unreadable functions csv: %s", functions_csv_path)
        return None
    return addresses


def _load_basicblock_address_set(acfg_json_path):
    addresses = set()

    try:
        with acfg_json_path.open("r", encoding="utf-8") as acfg_file:
            data = json.load(acfg_file)
    except (OSError, json.JSONDecodeError):
        logger.warning("Unreadable ACFG json: %s", acfg_json_path)
        return None

    def _add_addr(value):
        addr = _to_int_or_none(value)
        if addr is not None:
            addresses.add(addr)

    def _walk(node):
        if isinstance(node, dict):
            maybe_nodes = node.get("nodes")
            if isinstance(maybe_nodes, list):
                for entry in maybe_nodes:
                    _add_addr(entry)

            maybe_basic_blocks = node.get("basic_blocks")
            if isinstance(maybe_basic_blocks, dict):
                for bb_addr in maybe_basic_blocks.keys():
                    _add_addr(bb_addr)

            for child in node.values():
                _walk(child)
        elif isinstance(node, list):
            for child in node:
                _walk(child)

    _walk(data)
    return addresses


def collect_function_sets(results_folder, tool_name):
    function_sets = {}
    pattern = f"*_{tool_name}_functions.csv"

    for csv_path in results_folder.rglob(pattern):
        relative_dir = csv_path.relative_to(results_folder).parent
        binary_name = csv_path.stem.replace(f"_{tool_name}_functions", "")
        firmware, mode, severity, trial = parse_case_metadata(relative_dir, binary_name)
        if not firmware or not mode:
            continue
        key = (firmware, mode, severity, trial)
        addresses = _load_function_address_set(csv_path)
        if addresses is None:
            continue
        function_sets.setdefault(key, set()).update(addresses)

    return function_sets


def collect_basicblock_sets(results_folder, tool_name):
    block_sets = {}
    pattern = f"*_{tool_name}_acfg.json"

    for acfg_path in results_folder.rglob(pattern):
        relative_dir = acfg_path.relative_to(results_folder).parent
        binary_name = acfg_path.stem.replace(f"_{tool_name}_acfg", "")
        firmware, mode, severity, trial = parse_case_metadata(relative_dir, binary_name)
        if not firmware or not mode:
            continue
        key = (firmware, mode, severity, trial)
        addresses = _load_basicblock_address_set(acfg_path)
        if addresses is None:
            continue
        block_sets.setdefault(key, set()).update(addresses)

    return block_sets


def _tool_ran(row, tool_name):
    """A summary JSON was parsed for this tool, so a missing functions.csv /
    acfg.json means "recovered nothing", not "no data"."""
    return _to_float_or_none(row.get(f"{tool_name}_num_blocks")) is not None


def apply_function_relative_metrics(rows, tool_name, function_sets):
    baseline_by_trial = {}
    baseline_by_firmware_mode = {}

    for (firmware, mode, severity, trial), addresses in function_sets.items():
        if not addresses:
            continue
        if not _is_baseline_case(severity, trial):
            continue
        baseline_by_trial[(firmware, mode, trial)] = addresses
        baseline_by_firmware_mode.setdefault((firmware, mode), addresses)

    retention_key = f"{tool_name}_function_retention"
    ratio_key = f"{tool_name}_function_ratio"
    for row in rows:
        firmware = row.get("firmware", "")
        mode = row.get("mode", "")
        severity = row.get("severity", "")
        trial = row.get("trial", "")

        current = function_sets.get((firmware, mode, severity, trial))
        if current is None:
            if not _tool_ran(row, tool_name):
                row[retention_key] = ""
                row[ratio_key] = ""
                continue
            current = set()

        baseline = baseline_by_trial.get((firmware, mode, trial))
        if baseline is None:
            baseline = baseline_by_firmware_mode.get((firmware, mode))
        if not baseline:
            row[retention_key] = ""
            row[ratio_key] = ""
            continue

        baseline_count = len(baseline)
        intersection_count = len(current.intersection(baseline))
        row[retention_key] = _format_average(intersection_count / baseline_count)
        row[ratio_key] = _format_average(len(current) / baseline_count)


def apply_basicblock_relative_metrics(rows, tool_name, block_sets):
    baseline_by_trial = {}
    baseline_by_firmware_mode = {}

    for (firmware, mode, severity, trial), addresses in block_sets.items():
        if not addresses:
            continue
        if not _is_baseline_case(severity, trial):
            continue
        baseline_by_trial[(firmware, mode, trial)] = addresses
        baseline_by_firmware_mode.setdefault((firmware, mode), addresses)

    retention_key = f"{tool_name}_basicblock_retention"
    ratio_key = f"{tool_name}_basicblock_ratio"
    for row in rows:
        firmware = row.get("firmware", "")
        mode = row.get("mode", "")
        severity = row.get("severity", "")
        trial = row.get("trial", "")

        current = block_sets.get((firmware, mode, severity, trial))
        if current is None:
            if not _tool_ran(row, tool_name):
                row[retention_key] = ""
                row[ratio_key] = ""
                continue
            current = set()

        baseline = baseline_by_trial.get((firmware, mode, trial))
        if baseline is None:
            baseline = baseline_by_firmware_mode.get((firmware, mode))
        if not baseline:
            row[retention_key] = ""
            row[ratio_key] = ""
            continue

        baseline_count = len(baseline)
        intersection_count = len(current.intersection(baseline))
        row[retention_key] = _format_average(intersection_count / baseline_count)
        row[ratio_key] = _format_average(len(current) / baseline_count)


def build_trial_averages(rows):
    grouped = {}
    baselines = {}
    for row in rows:
        trial_name = str(row.get("trial", "")).lower()
        key = (row["firmware"], row["mode"], row["severity"])

        if trial_name == BASELINE_TRIAL:
            baselines[key] = row
            continue

        if trial_name in TRIALS_TO_AVERAGE:
            grouped.setdefault(key, []).append(row)

    average_rows = []
    for key, trial_rows in grouped.items():
        firmware, mode, severity = key
        avg_row = {
            "firmware": firmware,
            "mode": mode,
            "severity": severity,
            "trial_count": len(trial_rows),
        }

        for metric in METRIC_COLUMNS:
            values = []
            for trial_row in trial_rows:
                number = _to_float_or_none(trial_row.get(metric))
                if number is not None:
                    values.append(number)

            avg_row[metric] = _format_average(sum(values) / len(values)) if values else ""

        average_rows.append(avg_row)

    for key, baseline_row in baselines.items():
        firmware, mode, severity = key
        avg_row = {
            "firmware": firmware,
            "mode": mode,
            "severity": severity,
            "trial_count": 1,
        }

        for metric in METRIC_COLUMNS:
            avg_row[metric] = baseline_row.get(metric, "")

        average_rows.append(avg_row)

    average_rows.sort(
        key=lambda row: (
            row["firmware"],
            row["mode"],
            severity_sort_value(row["severity"]),
        )
    )
    return average_rows


def _group_average_rows(average_rows):
    grouped = {}
    for row in average_rows:
        key = (row["mode"], row["severity"])
        grouped.setdefault(key, []).append(row)
    return grouped


def build_macro_averages(average_rows):
    grouped = _group_average_rows(average_rows)
    macro_rows = []

    for key, rows in grouped.items():
        mode, severity = key
        out_row = {
            "mode": mode,
            "severity": severity,
            "firmware_count": len(rows),
            "total_trial_count": sum(int(row.get("trial_count", 0) or 0) for row in rows),
        }

        for metric in METRIC_COLUMNS:
            values = []
            for row in rows:
                number = _to_float_or_none(row.get(metric))
                if number is not None:
                    values.append(number)
            out_row[metric] = _format_average(sum(values) / len(values)) if values else ""

        macro_rows.append(out_row)

    macro_rows.sort(key=lambda row: (row["mode"], severity_sort_value(row["severity"])))
    return macro_rows


def build_mode_disassembly_success(rows):
    grouped = {}

    for row in rows:
        mode = row.get("mode", "")
        if not mode:
            continue
        bucket = grouped.setdefault(
            mode,
            {
                "case_count": 0,
                "angr_values": [],
                "ghidra_values": [],
            },
        )
        bucket["case_count"] += 1

        angr_value = _to_float_or_none(row.get("angr_disassembly_success"))
        if angr_value is not None:
            bucket["angr_values"].append(angr_value)

        ghidra_value = _to_float_or_none(row.get("ghidra_disassembly_success"))
        if ghidra_value is not None:
            bucket["ghidra_values"].append(ghidra_value)

    out_rows = []
    for mode, values in grouped.items():
        angr_values = values["angr_values"]
        ghidra_values = values["ghidra_values"]
        angr_percent = (sum(angr_values) / len(angr_values) * 100.0) if angr_values else None
        ghidra_percent = (sum(ghidra_values) / len(ghidra_values) * 100.0) if ghidra_values else None

        out_rows.append(
            {
                "mode": mode,
                "case_count": values["case_count"],
                "angr_case_count": len(angr_values),
                "angr_disassembly_success_percent": _format_average(angr_percent) if angr_percent is not None else "",
                "ghidra_case_count": len(ghidra_values),
                "ghidra_disassembly_success_percent": _format_average(ghidra_percent) if ghidra_percent is not None else "",
            }
        )

    out_rows.sort(key=lambda row: row["mode"])
    return out_rows


def parse_arguments():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Aggregate and compile all the output results",
    )
    parser.add_argument("results_folder", help="Path to results folder")
    parser.add_argument("output_folder", help="Path to output folder")
    return parser.parse_args()

def main():
    args = parse_arguments()
    results_folder = Path(args.results_folder)
    output_folder = Path(args.output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    if not results_folder.exists():
        raise FileNotFoundError(f"Results folder does not exist: {results_folder}")

    rows = collect_rows(results_folder)
    angr_basicblock_sets = collect_basicblock_sets(results_folder, "angr")
    ghidra_basicblock_sets = collect_basicblock_sets(results_folder, "ghidra")
    apply_basicblock_relative_metrics(rows, "angr", angr_basicblock_sets)
    apply_basicblock_relative_metrics(rows, "ghidra", ghidra_basicblock_sets)
    angr_function_sets = collect_function_sets(results_folder, "angr")
    ghidra_function_sets = collect_function_sets(results_folder, "ghidra")
    apply_function_relative_metrics(rows, "angr", angr_function_sets)
    apply_function_relative_metrics(rows, "ghidra", ghidra_function_sets)
    average_rows = build_trial_averages(rows)
    macro_rows = build_macro_averages(average_rows)
    mode_disassembly_rows = build_mode_disassembly_success(rows)

    csv_file_path = output_folder / f"static_results.csv"
    with csv_file_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(SUMMARY_COLUMNS)
        for row in rows:
            writer.writerow([row[column] for column in SUMMARY_COLUMNS])

    logger.info("Wrote %d rows to %s", len(rows), csv_file_path)

    avg_csv_file_path = output_folder / "static_results_trial_average.csv"
    with avg_csv_file_path.open("w", newline="", encoding="utf-8") as avg_csv_file:
        writer = csv.writer(avg_csv_file)
        writer.writerow(AVERAGE_COLUMNS)
        for row in average_rows:
            writer.writerow([row[column] for column in AVERAGE_COLUMNS])

    logger.info("Wrote %d rows to %s", len(average_rows), avg_csv_file_path)

    macro_csv_file_path = output_folder / "static_results_macro_average.csv"
    with macro_csv_file_path.open("w", newline="", encoding="utf-8") as macro_csv_file:
        writer = csv.writer(macro_csv_file)
        writer.writerow(AGGREGATE_COLUMNS)
        for row in macro_rows:
            writer.writerow([row[column] for column in AGGREGATE_COLUMNS])

    logger.info("Wrote %d rows to %s", len(macro_rows), macro_csv_file_path)

    mode_csv_file_path = output_folder / "static_results_mode_disassembly_success.csv"
    with mode_csv_file_path.open("w", newline="", encoding="utf-8") as mode_csv_file:
        writer = csv.writer(mode_csv_file)
        writer.writerow(MODE_DISASSEMBLY_COLUMNS)
        for row in mode_disassembly_rows:
            writer.writerow([row[column] for column in MODE_DISASSEMBLY_COLUMNS])

    logger.info("Wrote %d rows to %s", len(mode_disassembly_rows), mode_csv_file_path)

if __name__ == "__main__":
    main()

