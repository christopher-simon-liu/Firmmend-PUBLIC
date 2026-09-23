# Split Dataset

From Fuzzware:
- Using P2IM[1] for testing
- Using µEMU[2] (excluding the P2IM firmware) for training

# References

[1] Bo Feng, Alejandro Mera, and Long Lu. P2IM: Scalable and hardware-independent firmware testing via automatic peripheral interface modeling. In USENIX Security Symposium, 2020.

[2] Wei Zhou, Le Guan, Peng Liu, and Yuqing Zhang. Automatic firmware emulation through invalidity-guided knowledge inference. In 30th USENIX Security Symposium (USENIX Security 21). USENIX Association, 2021.


# Simulate extraction

Uses Dataset+Metadata.csv for target hardware flash size and base address
```bash
bash training_data/run_converter_all.sh
```

# Autoencoder repair pipeline

* `train_autoencoder.py` — trains a denoising byte autoencoder on a folder with
	binaries and saves the trained weights.
* `autoencoder_fill.py` — loads a trained model and ranks candidate bytes for
	each corrupted index using sliding-window reconstruction with overlap and
	soft-vote majority.

## 1. Train the model

```bash
python3 train_autoencoder.py <data_folder> <model_output.pt> \
	[--seq-len 64] [--stride 16] [--epochs 40] [--batch-size 64] \
	[--corruption-rate 0.15] [--embedding-dim 16] [--latent-dim 128] [--lr 1e-3]
```

The trainer walks every file directly under `<data_folder>`, slides a window
of `--seq-len` bytes with the given `--stride`, and treats every window as a
training sample. During each step, `--corruption-rate` of the bytes in the
input are replaced with uniformly random values while the original bytes
remain the reconstruction target. `--stride` defaults to `--seq-len`
(non-overlapping windows); a smaller stride yields more training samples per
file. The saved `.pt` file contains both the trained weights and the model
configuration (`seq_len`, `embedding_dim`, `latent_dim`), so the repair
script can rebuild the exact architecture.

```bash
python3 train_autoencoder.py training_data/extraction models/autoencoder.pt 
```

## 2. Repair a corrupted binary

```bash
python3 autoencoder_fill.py <indexes.csv> <corrupted.bin> <model.pt> \
	<output_folder> [--stride N] [--top-k 5] [--batch-size 128]
```

The repair script slides `seq_len`-byte windows across the corrupted binary
(with `--stride` defaulting to `seq_len // 4`, i.e. roughly four windows per
byte). Every window is fed through the autoencoder, and the resulting
softmax distributions are averaged across all windows that cover a given
position — a soft-vote majority across overlapping reconstructions. For each
index listed in the input CSV, the top `--top-k` bytes from that averaged
distribution are written as ranked candidates.

The output file is named `<stem>.autoencoder_fill.repair.csv` and has one row
per (index, rank) pair:

| column           | meaning                                                     |
| ---------------- | ----------------------------------------------------------- |
| `index`          | byte offset in the corrupted binary                         |
| `corrupted_byte` | value currently at that offset (`-1` if out of bounds)      |
| `rank`           | 1-based rank of the candidate (1 is the model's top pick)   |
| `candidate_byte` | predicted replacement byte in `0..255`                      |
| `score`          | averaged softmax probability for that byte across windows   |
| `windows`        | number of overlapping windows that voted on this index      |

Indexes that fall outside the binary, or that no window can cover (only
possible when the binary is shorter than `seq_len`), are emitted once with
`candidate_byte = -1` and `windows = 0`.

Example — repair the drone bit-flip test binary with a model trained above:

## Tuning notes

* **`--seq-len`** must match between training and inference (the repair
	script reads it from the checkpoint).
* **`--stride` at inference** trades runtime for redundancy. Smaller strides
	give more overlapping votes per byte (and stronger majority signals) but
	require more forward passes.
* **`--top-k`** only affects the number of rows in the output; the ranking is
	computed over all 256 possible bytes regardless.
