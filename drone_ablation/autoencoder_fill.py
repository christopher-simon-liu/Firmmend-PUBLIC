#!/usr/bin/env python3
"""Repair corrupted firmware bytes with a denoising byte autoencoder.

The corrupted binary is scanned with a sliding window. Overlapping windows
produce independent predictions for every byte position; the softmax
probabilities are averaged across all windows that cover a given position
(soft-vote majority) and the resulting distribution is used to rank
candidate replacement bytes for the indexes listed in the input CSV.
"""

import argparse
import bisect
import csv
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class ByteAutoencoder(nn.Module):
    """Must match the architecture used in ``train_autoencoder.py``."""

    def __init__(self, seq_len=64, embedding_dim=16, latent_dim=128):
        super().__init__()

        self.seq_len = seq_len

        self.embedding = nn.Embedding(num_embeddings=256, embedding_dim=embedding_dim)

        input_dim = seq_len * embedding_dim

        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 1024), nn.ReLU(), nn.Linear(1024, latent_dim)
        )

        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 1024), nn.ReLU(), nn.Linear(1024, seq_len * 256)
        )

    def forward(self, x):
        emb = self.embedding(x)
        emb = emb.view(x.size(0), -1)

        latent = self.encoder(emb)

        logits = self.decoder(latent)
        logits = logits.view(x.size(0), self.seq_len, 256)

        return logits


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Rank replacement bytes for corrupted positions using a "
                    "denoising byte autoencoder with sliding-window voting"
    )
    parser.add_argument("indexes", help="Path to the index-only CSV file")
    parser.add_argument("binary", help="Path to the corrupted binary file")
    parser.add_argument("model", help="Path to the trained autoencoder (.pt)")
    parser.add_argument("output_folder", help="Path to the output folder")
    parser.add_argument("--stride", type=int, default=None,
                        help="Sliding-window stride (default: seq_len // 4)")
    parser.add_argument("--top-k", type=int, default=5,
                        help="Ranked candidates to write per index (default: 5)")
    parser.add_argument("--batch-size", type=int, default=128,
                        help="Windows per inference batch (default: 128)")
    return parser.parse_args()


def load_indexes(indexes_path: Path):
    with indexes_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.reader(csv_file)
        next(reader, None)
        return [int(row[0]) for row in reader if row]


def load_model(model_path: Path, device):
    checkpoint = torch.load(model_path, map_location=device)
    config = checkpoint["config"]
    model = ByteAutoencoder(
        seq_len=config["seq_len"],
        embedding_dim=config["embedding_dim"],
        latent_dim=config["latent_dim"],
    ).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model, config["seq_len"]


def window_starts(binary_len, seq_len, stride):
    """Start offsets that fully cover ``[0, binary_len)`` with the given stride."""
    if binary_len < seq_len:
        return []

    starts = list(range(0, binary_len - seq_len + 1, stride))
    if starts[-1] != binary_len - seq_len:
        starts.append(binary_len - seq_len)
    return starts


def accumulate_probs(model, binary, seq_len, stride, indexes, batch_size, device):
    """Slide windows across ``binary`` and sum per-position softmax votes.

    Returns a dict mapping each requested index to (sum_of_prob_vectors,
    number_of_windows_that_covered_it).
    """
    binary_arr = np.frombuffer(binary, dtype=np.uint8)
    binary_len = len(binary_arr)

    needed_sorted = sorted({i for i in indexes if 0 <= i < binary_len})
    prob_sum = {i: np.zeros(256, dtype=np.float64) for i in needed_sorted}
    counts = {i: 0 for i in needed_sorted}

    starts = window_starts(binary_len, seq_len, stride)

    for batch_begin in range(0, len(starts), batch_size):
        batch_starts = starts[batch_begin:batch_begin + batch_size]
        windows = np.stack([binary_arr[s:s + seq_len] for s in batch_starts])
        x = torch.from_numpy(windows.astype(np.int64)).to(device)

        with torch.no_grad():
            logits = model(x)
            probs = F.softmax(logits, dim=-1).cpu().numpy()

        for wi, s in enumerate(batch_starts):
            lo = bisect.bisect_left(needed_sorted, s)
            hi = bisect.bisect_left(needed_sorted, s + seq_len)
            for pos in needed_sorted[lo:hi]:
                prob_sum[pos] += probs[wi, pos - s]
                counts[pos] += 1

    return prob_sum, counts


def main():
    args = parse_arguments()
    indexes_path = Path(args.indexes)
    binary_path = Path(args.binary)
    model_path = Path(args.model)
    output_folder = Path(args.output_folder)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    indexes = load_indexes(indexes_path)
    binary = binary_path.read_bytes()
    model, seq_len = load_model(model_path, device)

    stride = args.stride if args.stride is not None else max(1, seq_len // 4)
    top_k = max(1, min(args.top_k, 256))

    prob_sum, counts = accumulate_probs(
        model, binary, seq_len, stride, indexes, args.batch_size, device
    )

    output_folder.mkdir(parents=True, exist_ok=True)
    output_path = output_folder / f"{binary_path.stem}.autoencoder_fill.repair.csv"

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            ["index", "corrupted_byte", "rank", "candidate_byte", "score", "windows"]
        )

        for index in indexes:
            corrupted_byte = (
                binary[index] if 0 <= index < len(binary) else -1
            )

            if index not in counts or counts[index] == 0:
                writer.writerow([index, corrupted_byte, 1, -1, 0.0, 0])
                continue

            probs = prob_sum[index] / counts[index]
            ranked = np.argsort(-probs)[:top_k]
            for rank, byte_value in enumerate(ranked, start=1):
                writer.writerow([
                    index,
                    corrupted_byte,
                    rank,
                    int(byte_value),
                    f"{probs[byte_value]:.6f}",
                    counts[index],
                ])

    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
