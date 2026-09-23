#!/usr/bin/env python3
"""Train a denoising byte autoencoder for firmware repair.

Extracts fixed-length byte windows from every file in a data folder, corrupts
a fraction of the bytes each step, and trains a byte-classification
autoencoder to reconstruct the originals. The trained weights and model
configuration are saved so ``autoencoder_fill.py`` can load them later.
"""

import argparse
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import time
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset


class ByteAutoencoder(nn.Module):
    """Binary autoencoder model treats each byte value as a class."""

    def __init__(self, seq_len=64, embedding_dim=16, latent_dim=128):
        super().__init__()

        self.seq_len = seq_len
        self.embedding_dim = embedding_dim
        self.latent_dim = latent_dim

        self.embedding = nn.Embedding(num_embeddings=256, embedding_dim=embedding_dim)

        input_dim = seq_len * embedding_dim

        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 1024), nn.ReLU(), nn.Linear(1024, latent_dim)
        )

        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 1024), nn.ReLU(), nn.Linear(1024, seq_len * 256)
        )

    def forward(self, x):
        # x shape: (batch, seq_len)
        emb = self.embedding(x)
        emb = emb.view(x.size(0), -1)

        latent = self.encoder(emb)

        logits = self.decoder(latent)
        logits = logits.view(x.size(0), self.seq_len, 256)

        return logits


def extract_chunks(file_path, seq_len, stride):
    """Slide a window across the file and yield uint8 chunks of length ``seq_len``."""
    with open(file_path, "rb") as f:
        data = np.frombuffer(f.read(), dtype=np.uint8)

    if len(data) < seq_len:
        return []

    chunks = [data[start:start + seq_len]
              for start in range(0, len(data) - seq_len + 1, stride)]
    return chunks


def load_dataset(folder, seq_len, stride):
    """Load byte chunks from every ``.bin`` file under ``folder``, recursing into subfolders."""
    all_chunks = []

    for fp in sorted(Path(folder).rglob("*.bin")):
        if fp.is_file():
            print("Reading: %s" % fp)
            all_chunks.extend(extract_chunks(fp, seq_len, stride))

    return np.array(all_chunks, dtype=np.uint8)


def corrupt_bytes(batch, corruption_rate=0.15):
    """Replace ``corruption_rate`` of positions with uniformly random bytes."""
    corrupted = batch.clone()

    mask = torch.rand_like(corrupted.float()) < corruption_rate

    random_bytes = torch.randint(0, 256, corrupted.shape, device=corrupted.device)

    corrupted[mask] = random_bytes[mask]

    return corrupted, mask


def format_duration(seconds):
    """Format a duration as hours, minutes, and seconds."""
    seconds = max(0, int(seconds))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def print_progress(step, total_steps, loss, start_time, width=30):
    """Print one in-place training progress update."""
    elapsed = time.monotonic() - start_time
    average_step_time = elapsed / step
    remaining = average_step_time * (total_steps - step)
    fraction = step / total_steps
    complete = int(width * fraction)
    bar = "#" * complete + "-" * (width - complete)
    print(
        f"\r[{bar}] {fraction:6.1%} | loss {loss:.4f} | "
        f"elapsed {format_duration(elapsed)} | ETA {format_duration(remaining)}",
        end="",
        flush=True,
    )


class BinaryDataset(Dataset):
    """Class to represent dataset of byte chunks."""

    def __init__(self, chunks):
        self.chunks = torch.tensor(chunks, dtype=torch.long)

    def __len__(self):
        return len(self.chunks)

    def __getitem__(self, idx):
        return self.chunks[idx]


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Train a denoising byte autoencoder on a folder of binaries"
    )
    parser.add_argument("data_folder", help="Folder of binary training samples")
    parser.add_argument("model_output", help="Path to save the trained model (.pt)")
    parser.add_argument("--seq-len", type=int, default=64,
                        help="Length of each byte window (default: 64)")
    parser.add_argument("--embedding-dim", type=int, default=16,
                        help="Byte embedding dimensionality (default: 16)")
    parser.add_argument("--latent-dim", type=int, default=128,
                        help="Latent bottleneck dimensionality (default: 128)")
    parser.add_argument("--stride", type=int, default=None,
                        help="Stride for chunk extraction (default: seq_len)")
    parser.add_argument("--epochs", type=int, default=40,
                        help="Training epochs (default: 40)")
    parser.add_argument("--batch-size", type=int, default=64,
                        help="Training batch size (default: 64)")
    parser.add_argument("--lr", type=float, default=1e-3,
                        help="Adam learning rate (default: 1e-3)")
    parser.add_argument("--corruption-rate", type=float, default=0.15,
                        help="Fraction of bytes to randomize per training step "
                             "(default: 0.15)")
    return parser.parse_args()


def main():
    args = parse_arguments()

    stride = args.stride if args.stride is not None else args.seq_len

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    chunks = load_dataset(args.data_folder, args.seq_len, stride)
    if len(chunks) == 0:
        raise SystemExit(
            f"No chunks of length {args.seq_len} could be extracted from "
            f"{args.data_folder!r}."
        )
    print(f"Extracted {len(chunks)} chunks of length {args.seq_len}.")

    dataset = BinaryDataset(chunks)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)

    model = ByteAutoencoder(
        seq_len=args.seq_len,
        embedding_dim=args.embedding_dim,
        latent_dim=args.latent_dim,
    ).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    total_steps = len(loader) * args.epochs
    completed_steps = 0
    training_start = time.monotonic()

    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0

        for clean_batch in loader:
            clean_batch = clean_batch.to(device)

            corrupted_batch = corrupt_bytes(
                clean_batch, corruption_rate=args.corruption_rate
            )[0]

            logits = model(corrupted_batch)

            loss = F.cross_entropy(logits.view(-1, 256), clean_batch.view(-1))

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            completed_steps += 1
            print_progress(
                completed_steps,
                total_steps,
                loss.item(),
                training_start,
            )

        print(
            f"\rEpoch {epoch + 1}/{args.epochs}, "
            f"Loss {total_loss / len(loader):.4f}"
            + " " * 60
        )

    model_output = Path(args.model_output)
    model_output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config": {
                "seq_len": args.seq_len,
                "embedding_dim": args.embedding_dim,
                "latent_dim": args.latent_dim,
            },
        },
        model_output,
    )
    print(f"Saved trained model to {model_output}")


if __name__ == "__main__":
    main()
