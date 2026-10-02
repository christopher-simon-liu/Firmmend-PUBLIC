import argparse
import csv
import json
import logging
import os
import re
from pathlib import Path
from tqdm import tqdm

logger = logging.getLogger(__name__)

SUMMARY_COLUMNS = [
    "firmware",
    "mode",
    "severity",
    "trial",
    "binary_name",
    "boot_success",
    "num_blocks",
    "baseline_blocks",
    "corrupted_blocks",
    "coverage_ratio",
    "coverage_retention",
    "total_crash_traces",
    "crash_ratio",
    "crash_retention",
    "unique_crash_signatures",
    "unique_crash_blocks",
]

AVERAGE_COLUMNS = [
    "firmware",
    "mode",
    "severity",
    "binary_name",
    "trial_count",
    "boot_success",
    "num_blocks",
    "baseline_blocks",
    "corrupted_blocks",
    "coverage_ratio",
    "coverage_retention",
    "total_crash_traces",
    "crash_ratio",
    "crash_retention",
    "unique_crash_signatures",
    "unique_crash_blocks",
]

AGGREGATE_COLUMNS = [
    "mode",
    "severity",
    "firmware_count",
    "total_trial_count",
    "boot_success",
    "num_blocks",
    "baseline_blocks",
    "corrupted_blocks",
    "coverage_ratio",
    "coverage_retention",
    "total_crash_traces",
    "crash_ratio",
    "crash_retention",
    "unique_crash_signatures",
    "unique_crash_blocks",
]

MODE_BOOT_COLUMNS = [
    "mode",
    "case_count",
    "boot_case_count",
    "boot_success_percent",
]

METRIC_COLUMNS = [
    "boot_success",
    "num_blocks",
    "baseline_blocks",
    "corrupted_blocks",
    "coverage_ratio",
    "coverage_retention",
    "total_crash_traces",
    "crash_ratio",
    "crash_retention",
    "unique_crash_signatures",
    "unique_crash_blocks",
]
BASELINE_SEVERITY = "0.0"

CORRUPTED_BIN_PATTERN = re.compile(
    r"^(?P<firmware>.+)\.(?P<mode>[^.]+)-(?P<severity>[0-9]*\.?[0-9]+(?:[eE][-+]?\d+)?)\.bin$"
)


def load_summary(summary_path):
    """Load coverage data from *_fuzzware.json and merge crash data from *_fuzzware_crashes.json if present."""
    with summary_path.open("r", encoding="utf-8-sig") as summary_file:
        data = json.load(summary_file)

    result = {
        "binary_name": data.get("binary_name", ""),
        "boot_success": data.get("boot_success", ""),
        "num_blocks": data.get("num_blocks", ""),
        "baseline_blocks": data.get("baseline_blocks", ""),
        "corrupted_blocks": data.get("corrupted_blocks", ""),
        "coverage_ratio": data.get("coverage_ratio", ""),
        "coverage_retention": data.get("coverage_retention", ""),
    }

    # Try to load crash data from sibling *_fuzzware_crashes.json
    crash_path = summary_path.parent / summary_path.name.replace("_fuzzware.json", "_fuzzware_crashes.json")
    if crash_path.exists():
        try:
            with crash_path.open("r", encoding="utf-8") as crash_file:
                crash_data = json.load(crash_file)
            result["total_crash_traces"] = crash_data.get("total_crash_traces", "")
            result["unique_crash_signatures"] = crash_data.get("unique_crash_signatures", "")
            result["unique_crash_blocks"] = crash_data.get("unique_crash_blocks", "")
            crash_signature_set = crash_data.get("crash_signature_set", [])
            if isinstance(crash_signature_set, list):
                result["crash_signature_set"] = {str(item) for item in crash_signature_set}
            else:
                result["crash_signature_set"] = set()
        except (OSError, json.JSONDecodeError):
            result["total_crash_traces"] = ""
            result["unique_crash_signatures"] = ""
            result["unique_crash_blocks"] = ""
            result["crash_signature_set"] = set()
    else:
        result["total_crash_traces"] = ""
        result["unique_crash_signatures"] = ""
        result["unique_crash_blocks"] = ""
        result["crash_signature_set"] = set()

    result["crash_ratio"] = ""
    result["crash_retention"] = ""

    return result


def parse_corruption_metadata_from_binary_name(binary_name):
    if not binary_name:
        return "", "", ""

    match = CORRUPTED_BIN_PATTERN.match(Path(binary_name).name)
    if not match:
        return "", "", ""

    return match.group("firmware"), match.group("mode"), match.group("severity")


def parse_corruption_metadata(workdir_path):
    if not workdir_path.exists() or not workdir_path.is_dir():
        return "", "", ""

    parsed_candidates = []
    for bin_path in workdir_path.glob("*.bin"):
        match = CORRUPTED_BIN_PATTERN.match(bin_path.name)
        if match:
            parsed_candidates.append(
                (
                    match.group("firmware"),
                    match.group("mode"),
                    match.group("severity"),
                    bin_path.name,
                )
            )

    if not parsed_candidates:
        return "", "", ""

    parsed_candidates.sort(key=lambda item: item[3])
    firmware, mode, severity, _ = parsed_candidates[0]
    return firmware, mode, severity


def severity_sort_value(severity):
    if severity == "":
        return (1, 0.0)
    try:
        return (0, float(severity))
    except (TypeError, ValueError):
        return (1, 0.0)


def _to_float_or_none(value):
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_average(value):
    if value is None:
        return ""
    if value.is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def compute_crash_relative_metrics(rows):
    baseline_by_trial = {}
    baseline_by_firmware_mode = {}

    for row in rows:
        if not is_baseline_row(row):
            continue
        if not row.get("crash_signature_set"):
            continue
        baseline_by_trial[(row["firmware"], row["mode"], row["trial"])] = row
        baseline_by_firmware_mode.setdefault((row["firmware"], row["mode"]), row)

    for row in rows:
        signature_set = row.get("crash_signature_set")
        if not signature_set:
            row["crash_ratio"] = ""
            row["crash_retention"] = ""
            continue

        baseline_row = baseline_by_trial.get((row["firmware"], row["mode"], row["trial"]))
        if baseline_row is None:
            baseline_row = baseline_by_firmware_mode.get((row["firmware"], row["mode"]))
        if baseline_row is None:
            row["crash_ratio"] = ""
            row["crash_retention"] = ""
            continue

        baseline_set = baseline_row.get("crash_signature_set", set())
        baseline_count = len(baseline_set)
        current_count = len(signature_set)
        shared_count = len(signature_set.intersection(baseline_set))

        if baseline_count > 0:
            row["crash_ratio"] = _format_average(current_count / baseline_count)
            row["crash_retention"] = _format_average(shared_count / baseline_count)
        else:
            row["crash_ratio"] = "0"
            row["crash_retention"] = "0"


def is_baseline_row(row):
    return _to_float_or_none(row.get("severity")) == 0.0


def build_trial_averages(rows):
    grouped = {}
    baselines = {}

    for row in rows:
        key = (row["firmware"], row["mode"], row["severity"], row["binary_name"])
        if is_baseline_row(row):
            baselines[key] = row
            continue
        grouped.setdefault(key, []).append(row)

    average_rows = []

    for key, trial_rows in grouped.items():
        firmware, mode, severity, binary_name = key
        avg_row = {
            "firmware": firmware,
            "mode": mode,
            "severity": severity,
            "binary_name": binary_name,
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
        firmware, mode, severity, binary_name = key
        avg_row = {
            "firmware": firmware,
            "mode": mode,
            "severity": severity,
            "binary_name": binary_name,
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
            row["binary_name"],
        )
    )
    return average_rows


def build_macro_averages(average_rows):
    grouped = {}
    for row in average_rows:
        key = (row["mode"], row["severity"])
        grouped.setdefault(key, []).append(row)

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


def build_mode_boot_success(rows):
    grouped = {}

    for row in rows:
        mode = row.get("mode", "")
        if not mode:
            continue
        bucket = grouped.setdefault(
            mode,
            {
                "case_count": 0,
                "boot_values": [],
            },
        )
        bucket["case_count"] += 1

        boot_value = _to_float_or_none(row.get("boot_success"))
        if boot_value is not None:
            bucket["boot_values"].append(boot_value)

    out_rows = []
    for mode, values in grouped.items():
        boot_values = values["boot_values"]
        boot_percent = (sum(boot_values) / len(boot_values) * 100.0) if boot_values else None
        out_rows.append(
            {
                "mode": mode,
                "case_count": values["case_count"],
                "boot_case_count": len(boot_values),
                "boot_success_percent": _format_average(boot_percent) if boot_percent is not None else "",
            }
        )

    out_rows.sort(key=lambda row: row["mode"])
    return out_rows


def collect_rows_generator(results_folder):
    """Generator that yields rows from results folder as they are processed."""
    tqdm.write("Scanning for result files...")
    run_dirs = [p for p in results_folder.iterdir() if p.is_dir()]
    summary_files = [
        f
        for run_dir in run_dirs
        for f in run_dir.glob("*_fuzzware.json")
    ]
    tqdm.write(f"Found {len(summary_files)} result files.")

    for summary_path in tqdm(summary_files, desc="Processing summary files"):
        summary = load_summary(summary_path)
        trial = summary_path.parent.name

        firmware, mode, severity = parse_corruption_metadata_from_binary_name(
            summary["binary_name"]
        )

        if not firmware:
            workdir_path = summary_path.parent / "workdir"
            firmware, mode, severity = parse_corruption_metadata(workdir_path)

        if not firmware and summary["binary_name"]:
            firmware = Path(summary["binary_name"]).stem

        yield {
            "firmware": firmware,
            "mode": mode,
            "severity": severity,
            "trial": trial,
            "binary_name": summary["binary_name"],
            "boot_success": summary["boot_success"],
            "num_blocks": summary["num_blocks"],
            "baseline_blocks": summary["baseline_blocks"],
            "corrupted_blocks": summary["corrupted_blocks"],
            "coverage_ratio": summary["coverage_ratio"],
            "coverage_retention": summary["coverage_retention"],
            "total_crash_traces": summary["total_crash_traces"],
            "crash_ratio": summary["crash_ratio"],
            "crash_retention": summary["crash_retention"],
            "unique_crash_signatures": summary["unique_crash_signatures"],
            "unique_crash_blocks": summary["unique_crash_blocks"],
            "crash_signature_set": summary["crash_signature_set"],
        }


def parse_arguments():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Aggregate and compile all dynamic-analysis output results",
    )
    parser.add_argument(
        "results_folder",
        nargs="?",
        default="./output",
        help="Path to results folder (default: ./output)",
    )
    parser.add_argument(
        "output_folder",
        nargs="?",
        default="./output",
        help="Path to output folder (default: ./output)",
    )
    return parser.parse_args()


def trial_sort_key(trial):
    match = re.search(r"(\d+)$", trial)
    return int(match.group(1)) if match else float("inf")


def main():
    args = parse_arguments()
    results_folder = Path(args.results_folder)
    output_folder = Path(args.output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    if not results_folder.exists():
        raise FileNotFoundError(f"Results folder does not exist: {results_folder}")

    tqdm.write("Collecting rows...")
    rows = list(collect_rows_generator(results_folder))

    tqdm.write("Sorting by trial...")
    rows.sort(key=lambda row: trial_sort_key(row["trial"]))

    tqdm.write("Computing crash ratio/retention...")
    compute_crash_relative_metrics(rows)

    tqdm.write("Building trial averages...")
    average_rows = build_trial_averages(rows)

    tqdm.write("Building macro averages...")
    macro_rows = build_macro_averages(average_rows)

    tqdm.write("Building mode boot-success percentages...")
    mode_boot_rows = build_mode_boot_success(rows)

    csv_file_path = output_folder / "dynamic_results.csv"
    with csv_file_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(SUMMARY_COLUMNS)
        for row in rows:
            writer.writerow([row[column] for column in SUMMARY_COLUMNS])

    tqdm.write(f"Wrote {len(rows)} rows to {csv_file_path}")

    avg_csv_file_path = output_folder / "dynamic_results_trial_average.csv"
    with avg_csv_file_path.open("w", newline="", encoding="utf-8") as avg_csv_file:
        writer = csv.writer(avg_csv_file)
        writer.writerow(AVERAGE_COLUMNS)
        for row in average_rows:
            writer.writerow([row[column] for column in AVERAGE_COLUMNS])

    tqdm.write(f"Wrote {len(average_rows)} rows to {avg_csv_file_path}")

    macro_csv_file_path = output_folder / "dynamic_results_macro_average.csv"
    with macro_csv_file_path.open("w", newline="", encoding="utf-8") as macro_csv_file:
        writer = csv.writer(macro_csv_file)
        writer.writerow(AGGREGATE_COLUMNS)
        for row in macro_rows:
            writer.writerow([row[column] for column in AGGREGATE_COLUMNS])

    tqdm.write(f"Wrote {len(macro_rows)} rows to {macro_csv_file_path}")

    mode_csv_file_path = output_folder / "dynamic_results_mode_boot_success.csv"
    with mode_csv_file_path.open("w", newline="", encoding="utf-8") as mode_csv_file:
        writer = csv.writer(mode_csv_file)
        writer.writerow(MODE_BOOT_COLUMNS)
        for row in mode_boot_rows:
            writer.writerow([row[column] for column in MODE_BOOT_COLUMNS])

    tqdm.write(f"Wrote {len(mode_boot_rows)} rows to {mode_csv_file_path}")


if __name__ == "__main__":
    main()
