# FirmMend
Repairing Corrupted Firmware

This project analyzes, repairs, and evaluates corrupted firmware binaries. The workflow is:

1. Render pixel-art and provenance views of binaries.
2. Identify corrupted byte locations and generate index CSVs.
3. Apply a repair method to produce a mended binary.
4. Rewrite the repaired output and evaluate the result.
5. Compare output quality with diff, manifest, and static-analysis tooling.

## Table of Contents
- [Quick Start](#quick-start)
- [Binary Visualization](#binary-visualization)
- [Repair Methods](#repair-methods)
- [Rewrite Repaired Binaries](#rewrite-repaired-binaries)
- [Batch Workflows](#batch-workflows)
- [Diff and Manifest Outputs](#diff-and-manifest-outputs)
- [Static Analysis](#static-analysis)
- [Repository Layout](#repository-layout)

## Quick Start
A typical end-to-end run looks like this:

```bash
./scripts/run_provenance_all.sh firmcorr/dataset/extraction firmcorr/dataset/corruption
./scripts/run_repair_all.sh --method zero_fill
./scripts/run_diff_all.sh ./repairs/zero_fill
./scripts/run_manifest_all.sh
```

Use the single-binary scripts for targeted inspection and repair of one firmware sample.

## Binary Visualization

### Pixel Art Binary Representation
Render a binary into a 2D pixel-art visualization:

```bash
./scripts/run_pixel_art.sh ./firmcorr/dataset/extraction/Drone ./figures
./scripts/run_pixel_art_all.sh firmcorr/dataset/corruption
```

Pixel-art outputs include `.png` and `.svg` files for each binary.

### Corruption Provenance Pixel Art
Provenance compares a clean binary and a corrupted binary at the byte level:

```bash
./scripts/run_provenance.sh \
  ./firmcorr/dataset/extraction/Drone \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo \
  ./figures
./scripts/run_provenance_all.sh firmcorr/dataset/extraction firmcorr/dataset/corruption
```

Provenance outputs include `.png`, `.svg`, and a CSV listing each mismatched byte:

```text
index,original_byte,corrupted_byte
```

- `index` is the zero-based byte offset.
- `original_byte` and `corrupted_byte` are integers in the range `0` to `255`.
- A value of `-1` means the byte is missing because one binary is shorter than the other.

The tool also emits 1D variants (`.provenance.1d.png` and `.provenance.1d.svg`) for long or tall binaries that are difficult to inspect in 2D.

> Provenance analysis must be run before repair to generate the required `*.indexes.csv` files.

## Repair Methods
Repair scripts accept three inputs: a CSV containing corrupted byte indexes (`*.indexes.csv`), a corrupted binary, and an output folder.

### No Repair
No change. The corrupted bytes remain the same in the output.

### Zero Fill
Each corrupted index is replaced with `0x00`.

```bash
./scripts/run_repair.sh --method zero_fill \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/figures/Drone.bin.indexes.csv \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.bin \
  ./repairs/zero_fill/Drone/bit_flip_0.01_congroo
```

The repair CSV is written as `<binary-name>.zero_fill.repair.csv`.

### Local Fill
For each corrupted index, the method averages the nearest valid bytes to the left and right. If a neighboring byte is unavailable, the candidate is `-1`.

```bash
./scripts/run_repair.sh --method local_fill \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/figures/Drone.bin.indexes.csv \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.bin \
  ./repairs/local_fill/Drone/bit_flip_0.01_congroo
```

The repair CSV is written as `<binary-name>.local_fill.repair.csv`.

### Oracle Donor
This oracle baseline uses the original clean binary as the source of replacement values. If an index is outside either binary, the candidate is written as `-1`.

```bash
./scripts/run_repair.sh --method oracle_donor \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/figures/Drone.bin.indexes.csv \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.bin \
  ./firmcorr/dataset/extraction/Drone/Drone.bin \
  ./repairs/oracle_donor/Drone/bit_flip_0.01_congroo
```

The repair CSV is written as `<binary-name>.oracle_donor.repair.csv`.

### ISA-Aware NOP Fill
The NOP repair method requires an explicit ISA because multi-byte instruction encodings must be emitted in the correct byte order. Supported ISAs include `arm`, `arm-thumb`, `mips`, `riscv`, and `x86`.

```bash
./scripts/run_repair.sh --method nop_fill --isa arm-thumb \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/figures/Drone.bin.indexes.csv \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.bin \
  ./repairs/nop_fill/Drone/bit_flip_0.01_congroo
```

For a multi-byte NOP, valid mismatched indexes must form complete consecutive groups matching the NOP encoding size. Each valid group receives the corresponding NOP bytes; isolated, non-consecutive, or incomplete groups receive `-1`.

The output is written as `<binary-name>.nop_fill.repair.csv`.

### Denoising Autoencoder Fill
The autoencoder method uses a trained denoising byte autoencoder (`src/repair/denoising_autoencoder/autoencoder_fill.py`) to predict replacements. The corrupted binary is scanned with overlapping sliding windows; softmax probabilities over all windows covering a byte are averaged and ranked to select the most likely replacement for each corrupted index.

```bash
./scripts/run_repair_autoencoder.sh \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/figures/Drone.bin.indexes.csv \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.bin \
  ./repairs/autoencoder_fill/Drone/bit_flip_0.01_congroo
```

The default model is used when `--model` is omitted:

```bash
./scripts/run_repair_autoencoder.sh \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/figures/Drone.bin.indexes.csv \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.bin \
  ./repairs/autoencoder_fill/Drone/bit_flip_0.01_congroo
```

`--model` defaults to `src/repair/denoising_autoencoder/models/autoencoder.pt` and can be overridden with a differently trained checkpoint. `--stride`, `--top-k`, and `--batch-size` are forwarded to `autoencoder_fill.py`; training and tuning details are documented in `src/repair/denoising_autoencoder/Notes.md`.

The full ranked output is written as `<binary-name>.autoencoder_fill.ranked.csv`; the wrapper then filters the best-ranked row for each index into `<binary-name>.autoencoder_fill.repair.csv` before rewriting the binary.

## Rewrite Repaired Binaries
Use `src/util/rewrite.py` to apply a repair CSV to a corrupted binary. Candidate values of `-1` are skipped because no repair was available. The output file is created in the output folder using the same base name, replacing `repair.csv` with `mend.bin`.

Example:

```bash
python3 src/util/rewrite.py \
  ./repairs/oracle_donor/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.oracle_donor.repair.csv \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.bin \
  ./repairs/oracle_donor/Drone/bit_flip_0.01_congroo
```

For partial dumps, rows targeting indexes beyond the current binary size can extend the binary tail when provenance indicates the source byte is unknown. If either `original_byte` or `corrupted_byte` is `-1`, `rewrite.py` pads missing bytes with `0xFF` up to the target index before applying the replacement byte. Out-of-range rows without evidence of a missing byte are rejected.

## Batch Workflows

### Batch Repair
`./scripts/run_repair_all.sh` walks a corrupted-binary tree and runs `run_repair.sh` for each `.bin` it finds. It locates the matching `*.indexes.csv` in either the binary folder or its `figures/` subfolder and mirrors the layout under `REPAIRS_ROOT/<method>/<firmware>/<corruption>/`.

```text
Usage: ./scripts/run_repair_all.sh --method METHOD [--isa ISA] [--original-root DIR] [INPUT_ROOT] [REPAIRS_ROOT]
```

Examples:

```bash
./scripts/run_repair_all.sh --method no_repair
./scripts/run_repair_all.sh --method zero_fill
./scripts/run_repair_all.sh --method local_fill
./scripts/run_repair_all.sh --method nop_fill --isa arm-thumb
./scripts/run_repair_all.sh --method oracle_donor
```

Notes:
- `INPUT_ROOT` defaults to `firmcorr/dataset/corruption`.
- `ORIGINAL_ROOT` defaults to `firmcorr/dataset/extraction`.
- `REPAIRS_ROOT` defaults to `./repairs`.
- `--isa` is forwarded to `nop_fill`.
- `--original-root` is required for `oracle_donor`.
- If a binary lacks an index CSV (or, for `oracle_donor`, a matching original), it is skipped with a warning.
- When a directory contains `Metadata.json`, the script pads a temporary copy with `0xFF` to the declared `flash_size` before repair, preserving the full flash size without modifying the source.

`run_repair_autoencoder_all.sh` is the equivalent batch wrapper for the autoencoder method:

```text
Usage: ./scripts/run_repair_autoencoder_all.sh [--model MODEL_PT] [--stride N] [--top-k N] [--batch-size N] [INPUT_ROOT] [REPAIRS_ROOT]
```

Example:

```bash
./scripts/run_repair_autoencoder_all.sh firmcorr/dataset/corruption repairs/autoencoder_fill
```

## Diff and Manifest Outputs

### Repair Diff
`run_diff.sh` wraps `src/util/diff.py` to compare a corrupted binary against a repaired one and visualize the changes. The signed byte-wise difference is `corrupted - mended`; the shorter input is padded with `0xFF` so both streams align.

```text
Usage: ./scripts/run_diff.sh <corrupted_binary> <mended_binary> <output_folder> [options]
```

Example:

```bash
./scripts/run_diff.sh \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.bin \
  ./repairs/zero_fill/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.zero_fill.mend.bin \
  ./repairs/zero_fill/Drone/bit_flip_0.01_congroo/figures
```

Use `--width` to change the number of bytes per row (default `512`). Output files include:

```text
<binary-name>.diff.png
<binary-name>.diff.svg
<binary-name>.diff.1d.png
<binary-name>.diff.1d.svg
<binary-name>.diff.csv
<binary-name>.diff.indexes.csv
```

Only bytes with a non-zero difference appear in the CSVs. A value of `-1` indicates the index is past the end of that binary.

Batch diffing is handled by `./scripts/run_diff_all.sh`:

```text
Usage: ./scripts/run_diff_all.sh [--width N] [MEND_ROOT] [CORRUPTED_ROOT] [OUTPUT_ROOT]
```

Examples:

```bash
./scripts/run_diff_all.sh ./repairs/zero_fill
./scripts/run_diff_all.sh ./repairs/local_fill
./scripts/run_diff_all.sh ./repairs/nop_fill
./scripts/run_diff_all.sh ./repairs/oracle_donor
./scripts/run_diff_all.sh ./repairs/autoencoder_fill
```

Without `OUTPUT_ROOT`, results are written to `<mend-folder>/figures`. With `OUTPUT_ROOT`, the layout is mirrored under that path.

### Repair Manifest
`run_manifest.sh` wraps `src/util/manifest.py` to emit a `RepairCandidate` record describing how a repaired binary differs from the corrupted and original inputs.

```text
Usage: ./scripts/run_manifest.sh <mended_binary> <corrupted_binary> <original_binary> <output_folder> [options]
```

Example:

```bash
./scripts/run_manifest.sh \
  ./repairs/zero_fill/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.zero_fill.mend.bin \
  ./firmcorr/dataset/corruption/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.bin \
  ./firmcorr/dataset/extraction/Drone/Drone.bin \
  ./repairs/zero_fill/Drone/bit_flip_0.01_congroo
```

The output is written as `manifest.json`:

```json
{
  "input_sha256": "<sha256 of the corrupted binary>",
  "mask_id": "Drone.bit_flip-0.01.zero_fill",
  "method_name": "zero_fill",
  "parameters": {
    "mended_binary": "...",
    "corrupted_binary": "...",
    "original_binary": "..."
  },
  "edits": [
    {
      "offset": 1024,
      "original_byte": 18,
      "corrupted_byte": 19,
      "mend_bytes": [0]
    }
  ],
  "repair_correctness": {
    "total_corrupted_bytes": 1,
    "matching_mend_bytes": 0,
    "repair_correctness_ratio": 0.0
  },
  "output_sha256": "<sha256 of the mended binary>"
}
```

`mask_id` defaults to the mended binary name without `.mend.bin`, and `method_name` defaults to the final path component. Override both with `--mask-id` and `--method`. Extra parameters can be added with repeated `--parameter KEY=VALUE` arguments.

`repair_correctness` compares each offset that differs between the corrupted and original binaries. `total_corrupted_bytes` is the number of those offsets, `matching_mend_bytes` counts the corresponding mended bytes that equal the original bytes, and `repair_correctness_ratio` is `matching_mend_bytes / total_corrupted_bytes`. The ratio is `null` when no corrupted bytes are present.

This per-manifest summary covers the complete binary extent. For firmware-level comparisons, use the repair-correctness aggregation described below, which excludes non-firmware padding and other bytes outside the meaningful data range.

Batch manifest generation is handled by `./scripts/run_manifest_all.sh`:

```text
Usage: ./scripts/run_manifest_all.sh [--parameter KEY=VALUE]... [MEND_ROOT] [CORRUPTED_ROOT] [ORIGINAL_ROOT] [OUTPUT_ROOT]
```

Example:

```bash
./scripts/run_manifest_all.sh
./scripts/run_manifest_all.sh --parameter isa=arm-thumb
```

Without an `OUTPUT_ROOT`, each `manifest.json` is written next to its mended binary. With an output root, the input layout is mirrored beneath it.

### Repair Correctness Figures
Aggregate the `repair_correctness` summaries from generated manifests and create technique and severity comparisons:

```bash
./scripts/eval/create_repair_correctness_figures.sh repairs figures/repair_correctness
```

The command writes `repair_correctness.csv`, `repair_correctness_by_mode_severity.csv`, `repair_correctness_by_method_mode.csv`, `repair_correctness_overall.csv`, and the following SVG/PDF figures to the output folder:

- `repair_correctness_overall`: byte-weighted correctness by repair technique.
- `repair_correctness_by_mode_overall`: average correctness for each technique and corruption mode.
- `repair_correctness_by_severity`: a two-column overview of every corruption mode versus severity, with consistent technique colors and one shared legend.
- `repair_correctness_<mode>_by_severity`: a separate severity chart for each corruption mode, such as `repair_correctness_partial_write_by_severity.svg`.

For each manifest, aggregation reads the adjacent `Metadata.json` and recomputes correctness only within its meaningful firmware data range. Metadata values are flash addresses, while binary indexes are zero-based offsets, so the included half-open offset range is:

```text
[data_start - flash_start, data_end - flash_start)
```

When `flash_start` is `0`, this is simply `[data_start, data_end)`. Every index before the start or at/after the end is excluded from corrupted-byte totals and matching-byte totals. This prevents erased-flash padding, including `0xFF` tail padding introduced while handling partial dumps, from being counted as a successful repair. The per-manifest `repair_correctness.csv` records the applied `data_start_offset` and `data_end_offset` for auditability.

The method/mode CSV reports the arithmetic mean of non-null manifest ratios. The overall CSV and figure use the same byte-weighted correctness calculation. The severity figure groups results by corruption mode and numeric severity parsed from the corruption-folder name.

## Static Analysis
Static-analysis scripts evaluate the repaired binaries with angr and Ghidra, then aggregate the resulting metrics.

Examples:

```bash
./scripts/eval/static/run_angr.sh \
  repairs/zero_fill/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.zero_fill.mend.bin \
  results
./scripts/eval/static/run_angr_all.sh repairs results
```

```bash
./scripts/eval/static/run_ghidra.sh \
  repairs/zero_fill/Drone/bit_flip_0.01_congroo/Drone.bit_flip-0.01.zero_fill.mend.bin \
  results
./scripts/eval/static/run_ghidra_all.sh repairs results
```

```bash
./scripts/eval/static/run_aggregate.sh results figures
./scripts/eval/static/create_figures.sh figures/local_fill/static_results_macro_average.csv figures/local_fill
./scripts/eval/static/create_figures.sh figures/nop_fill/static_results_macro_average.csv figures/nop_fill
./scripts/eval/static/create_figures.sh figures/zero_fill/static_results_macro_average.csv figures/zero_fill
./scripts/eval/static/create_figures.sh figures/no_repair/static_results_macro_average.csv figures/no_repair
./scripts/eval/static/create_figures.sh figures/oracle_donor/static_results_macro_average.csv figures/oracle_donor
```

For the default-model autoencoder, run the separate repair tree and create its static-analysis figures:

```bash
./scripts/eval/static/run_angr_all.sh repairs/autoencoder_fill results/autoencoder_fill
./scripts/eval/static/run_ghidra_all.sh repairs/autoencoder_fill results/autoencoder_fill
./scripts/eval/static/run_aggregate.sh results figures
./scripts/eval/static/create_figures.sh figures/autoencoder_fill/static_results_macro_average.csv figures/autoencoder_fill
```

To compare a repair method against the oracle and unrepaired baselines, generate an overlay summary:

```bash
./scripts/eval/static/create_figures_compare.sh \
  figures/oracle_donor/static_results_macro_average.csv \
  figures/no_repair/static_results_macro_average.csv \
  figures/local_fill/static_results_macro_average.csv \
  figures/local_fill/compare

./scripts/eval/static/create_figures_compare.sh \
  figures/oracle_donor/static_results_macro_average.csv \
  figures/no_repair/static_results_macro_average.csv \
  figures/nop_fill/static_results_macro_average.csv \
  figures/nop_fill/compare

./scripts/eval/static/create_figures_compare.sh \
  figures/oracle_donor/static_results_macro_average.csv \
  figures/no_repair/static_results_macro_average.csv \
  figures/zero_fill/static_results_macro_average.csv \
  figures/zero_fill/compare

./scripts/eval/static/create_figures_compare.sh \
  figures/oracle_donor/static_results_macro_average.csv \
  figures/no_repair/static_results_macro_average.csv \
  figures/autoencoder_fill/static_results_macro_average.csv \
  figures/autoencoder_fill/compare
```

Aggregate the AUC comparison output:

```bash
scripts/eval/static/create_figures_auc.sh figures/auc_compare \
  figures/zero_fill/compare/static_results_auc_compare.csv \
  figures/nop_fill/compare/static_results_auc_compare.csv \
  figures/local_fill/compare/static_results_auc_compare.csv \
  figures/autoencoder_fill/compare/static_results_auc_compare.csv \
  --labels "Zero Fill" "NOP Fill" "Local Fill" "Autoencoder Fill"
```

## Repository Layout

```text
firmmend
├── firmcorr
│   └── dataset
│       ├── corruption
│       └── extraction
├── figures
├── repairs
│   └── <repair_method>
│       └── <firmware>
│           └── <corruption>
│               ├── Drone.bin.zero_fill.repair.csv
│               ├── Drone.bin.zero_fill.mend.bin
│               └── manifest.json
├── results
│   └── <repair_method>
│       └── <firmware>
│           └── <corruption>
│               ├── Drone.bin.zero_fill.mend.bin_angr.json
│               └── Drone.bin.zero_fill.mend.bin_ghidra.json
├── scripts
│   ├── eval
│   │   └── static
│   │       ├── create_figures.sh
│   │       ├── run_aggregate.sh
│   │       ├── run_angr.sh
│   │       ├── run_angr_all.sh
│   │       ├── run_ghidra.sh
│   │       └── run_ghidra_all.sh
│   ├── run_diff.sh
│   ├── run_diff_all.sh
│   ├── run_manifest.sh
│   ├── run_manifest_all.sh
│   ├── run_pixel_art.sh
│   ├── run_pixel_art_all.sh
│   ├── run_provenance.sh
│   ├── run_provenance_all.sh
│   ├── run_repair.sh
│   ├── run_repair_all.sh
│   ├── run_repair_autoencoder.sh
│   └── run_repair_autoencoder_all.sh
├── src
│   ├── repair
│   │   ├── denoising_autoencoder
│   │   │   └── autoencoder_fill.py
│   │   ├── local_fill.py
│   │   ├── nop_fill.py
│   │   ├── oracle_donor.py
│   │   └── zero_fill.py
│   └── util
│       ├── diff.py
│       ├── manifest.py
│       ├── provenance.py
│       └── rewrite.py
├── LICENSE
├── README.md
└── .gitignore
```