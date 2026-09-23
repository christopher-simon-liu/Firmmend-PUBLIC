# FirmCorr
Benchmarking the Robustness of Static and Dynamic Firmware Analysis Under Corruption

## Building the Dataset

### Simulating Firmware Extraction
Use Chip Reference Manuals/Datasheets for information on base addresses and flash memory sizes.
**Firmware Size <= Flash Memory Size**

Example run commands:
```bash
./scripts/run_converter.sh dataset/original/Drone dataset/extraction/Drone
./scripts/run_converter_all.sh dataset/original dataset/extraction
```

*All uses Dataset_Metadata.csv*

### Corruption Harness
Refer to **CORRUPTION_EXAMPLES** for explanations on corruption modes

Example run commands:
```bash
./scripts/run_corrupter.sh bit_flip 0.01 134217728, 134268148 dataset/extraction/Drone/Drone.bin dataset/corruption/Drone/partial_dump_0.01_congroo 1.048596
./scripts/run_corrupter_all.sh
```

*All uses experiment_matrix.csv*

### Pixel Art Binary Representation

Example run commands:
```bash
./scripts/run_pixel_art.sh dataset/extraction/Drone dataset/extraction/figures
./scripts/run_pixel_art_all.sh dataset/extraction
```
Pixel art outputs now include both `.png` and `.svg` files per binary.
## Corruption Provenance Pixel Art

Example run commands:
```bash
./scripts/run_provenance.sh dataset/extraction/Drone dataset/corruption/Drone/bit_flip_0.01_congroo dataset/corruption/Drone/bit_flip_0.01_congroo/figures
./scripts/run_provenance_all.sh dataset/extraction dataset/corruption
```
Provenance outputs now include `.png`, `.svg`, and mismatch-coordinate `.csv` files.

## Static Analysis 

Static analysis uses [Ghidra](https://github.com/NationalSecurityAgency/ghidra) and or [angr](https://github.com/angr/angr)
to disassemble each firmware image and measure how much of it can actually be reverse engineered under corruption.

Each firmware directory in the dataset contains a Metadata.json which contains the base address and size of the firmware.

For every firmware the pipeline produces, in the output directory:
* `<binary>_acfg.json` — Attribute Control Flow Graph with structural and semantic attributes of each basic block in the graph
* `<binary>_call_graph.dot` — plain-text graph description of of Function Call Graph 
* `<binary>_functions.csv` — list of identified functions
* `<binary>_<tool>.json` — summary with `binary_name`, `disassembly_success`, `num_blocks`, `num_edges`, and `num_functions`

### Testing angr
**python 3.8 required**

Docker container:
```bash
./scripts/build_angr.sh
```

Example run commands:
```bash
./scripts/run_angr.sh dataset/original/Drone/Drone.bin results 0x8000000
./scripts/run_angr_all.sh dataset/corruption results
```
### Testing Ghidra
**java required**

Docker container:
```bash
./scripts/build_ghidra.sh
```

Example run commands:
```bash
./scripts/run_ghidra.sh dataset/original/Drone/Drone.bin results 0x8000000
./scripts/run_ghidra_all.sh dataset/corruption results
```

### Aggregate Results
```bash
./scripts/run_aggregate.sh ./results ./results
```

### Create Figures
```bash 
./scripts/create_figures.sh ./results/static_results_macro_average.csv figures
```
This generates `.svg` and `.pdf` figures per mode by default.
PDFs are sized for two-column LaTeX by default (`--pdf-width-in 7.0`). To target a single column, use e.g. `--pdf-width-in 3.4`.
Text is scaled up for paper readability by default (`--text-scale 1.35`); adjust with `--text-scale` as needed.
PDF output is vector-only (CairoSVG or Inkscape required). PNG output is optional via `--with-png`.

## Dynamic Analysis

Dynamic analysis uses [Fuzzware](https://github.com/fuzzware-fuzzer/fuzzware) to fuzz each
firmware image and measure how much of it can actually be reached at runtime under corruption.

Each firmware directory in the dataset already ships the required Fuzzware artifacts next to
its binary: `config.yml`, `syms.yml`, a `base_inputs/` seed directory, and a
`valid_basic_blocks.txt` ground-truth basic-block listing.

For every firmware the pipeline produces, in the output directory:

* `<binary>_fuzzware.json` — summary with `binary_name`, `boot_success`, and `num_blocks`.
  `boot_success` is `1` when the run produced any covered basic blocks (`num_blocks > 0`),
  otherwise `0`.
* `<binary>_fuzzware_blocks.txt` — the sorted list of unique covered basic blocks (one bare
  hex address per line, the same format as `valid_basic_blocks.txt`) for future comparisons.
* `<binary>_fuzzware_stats/` — a copy of the Fuzzware pipeline statistics (best effort).

### Testing Fuzzware
**docker required** (the host kernel must allow AFL: set the core pattern once with
`sudo bash -c 'echo core > /proc/sys/kernel/core_pattern'`)

Docker container (builds the upstream `fuzzware:latest` base image automatically if missing,
then the `firmcorr-fuzzware` image on top):
```bash
./scripts/build_fuzzware.sh
```

Example run commands (the optional 3rd/4th arguments are the pipeline runtime in `DD:HH:MM:SS`
format and the number of local fuzzer instances; they default to `00:00:10:00` and `1`):
```bash
./scripts/run_fuzzware.sh dataset/extraction/Drone/Drone.bin results 00:00:10:00 1
./scripts/run_fuzzware_all.sh dataset/corruption results 00:00:10:00 1
```

`run_fuzzware_all.sh` discovers firmware by locating `config.yml` files, runs the binary each
config references, mirrors the input directory layout under the output directory, and skips
configurations whose `<binary>_fuzzware.json` already exists so runs are resumable.

### Smoke Test
```bash
sudo bash -c 'echo core > /proc/sys/kernel/core_pattern'
./scripts/build_fuzzware.sh
./scripts/run_fuzzware.sh dataset/extraction/Drone/Drone.bin results 00:00:05:00 1
```

### HPC Fuzzing

Docker container:
**build with fuzzware_entrypoint_hpc.sh instead**

Example run commands:
```bash
./generate_targets.sh
sbatch --array=1-500 fuzzware_array.slurm
```

### Post Processing

**calculate total coverage of a fuzzing campaign**

Example run commands:
```bash
./scripts/run_coverage_calc.sh  results/run_42 results/output
./scripts/run_coverage_calc_all.sh results results/output

./scripts/run_coverage_calc_plus.sh  results/run_42 results/output
./scripts/run_coverage_calc_plus_all.sh results results/output

# coverage_calc_plus uses the corresponding severity 0.0 fuzzware_blocks artifact
# as baseline for coverage_retention and coverage_overlap.

./scripts/run_crash_calc.sh  results/run_42 results/output
./scripts/run_crash_calc_all.sh results results/output
```

### Aggregate Results
```bash
./scripts/run_aggregate_fuzzing.sh ./results/output ./results
```

### Create Figures
```bash 
./scripts/create_figures_fuzzing.sh ./results/dynamic_results_macro_average.csv figures

# Coverage-change distribution boxplot (all dynamic runs by corruption mode)
./scripts/create_figures_coverage_box.sh ./results/dynamic_results.csv figures

# Crash-ratio distribution boxplot (all dynamic runs by corruption mode)
./scripts/create_figures_crash_box.sh ./results/dynamic_results.csv figures

# Static vs dynamic retention scatter (Ghidra vs Fuzzware)
./scripts/create_figures_compare.sh ./results/static_results.csv ./results/dynamic_results.csv figures

# Per-firmware coverage heatmap (universal vs concentrated effects)
./scripts/create_figures_coverage_heat.sh ./results/dynamic_results.csv figures

# Per-firmware crash-ratio heatmap (universal vs concentrated crash effects)
./scripts/create_figures_crash_heat.sh ./results/dynamic_results.csv figures
```
This generates `.svg` and `.pdf` figures per mode by default.
PDFs are sized for two-column LaTeX by default (`--pdf-width-in 7.0`). To target a single column, use e.g. `--pdf-width-in 3.4`.
Text is scaled up for paper readability by default (`--text-scale 1.35`); adjust with `--text-scale` as needed.
PDF output is vector-only (CairoSVG or Inkscape required). PNG output is optional via `--with-png`.
The coverage plotting command writes `dynamic_coverage_ratio_boxplot.svg/.pdf` and
`dynamic_coverage_ratio_violin_boxplot.svg/.pdf` by default.
It also writes `dynamic_coverage_ratio_distribution_stats.csv` with per-mode `n`, `median`, `q1`, `q3`, `iqr`, and `outlier_count`.
The crash-ratio plotting command writes `dynamic_crash_ratio_boxplot.svg/.pdf` and
`dynamic_crash_ratio_violin_boxplot.svg/.pdf` by default.
It also writes `dynamic_crash_ratio_distribution_stats.csv` with per-mode `n`, `median`, `q1`, `q3`, `iqr`, and `outlier_count`.
The coverage heat plotting command writes `dynamic_coverage_ratio_per_firmware_heatmap.svg/.pdf`.
The crash heat plotting command writes `dynamic_crash_ratio_per_firmware_heatmap.svg/.pdf`.
The compare plotting command writes `ghidra_vs_fuzzware_static_dynamic_scatter.svg/.pdf` and
`ghidra_vs_fuzzware_static_dynamic_scatter_by_mode.svg/.pdf`.

## File Tree
```
firmcorr
├── dataset
│   ├── corruption
│   ├── extraction
│   └── original
│       └── Dataset_Metadata.csv
├── figures
├── results
│   └── results.csv
├── scripts
│   └── run.sh
├── src
│   ├── corruption
│   │   ├── modes
│   │   │   └── bit_flip.py
│   │   └── corrupter.py
│   ├── measurement
│   │   ├── dynamic
│   │   │   ├── fuzzware_entrypoint.sh
│   │   │   └── fuzzware_summary.py
│   │   └── static
│   │       ├── docker_entrypoint.sh
│   │       └── acfg_disasm_stuff.py
│   ├── repair?
│   └── util
│       ├── aggregate.py
│       └── figures.py
├── experiment_matrix.csv
├── Dockerfile
├── batch.slurm
└── README.md
```

