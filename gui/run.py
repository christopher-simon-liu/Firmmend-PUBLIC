"""Host GUI for inspecting and mending corrupted firmware binaries."""

import csv
import math
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src" / "repair"))
sys.path.insert(0, str(REPO_ROOT / "src" / "util"))

import local_fill  # noqa: E402
import nop_fill  # noqa: E402
import rewrite  # noqa: E402

ROW_WIDTH = 512
PREVIEW_SIZE = (360, 360)

STRATEGIES = ("zero_fill", "nop_fill", "local_fill", "oracle_donor", "no_repair")


def load_indexes(indexes_path: Path):
    """Read corrupted byte indexes from a CSV file with or without a header."""
    indexes = []
    with indexes_path.open("r", newline="", encoding="utf-8") as csv_file:
        for row in csv.reader(csv_file):
            if not row or not row[0].strip():
                continue
            try:
                indexes.append(int(row[0].strip()))
            except ValueError:
                continue
    return indexes


def reshape_bytes(values, fill):
    size = len(values)
    height = max(math.ceil(size / ROW_WIDTH), 1)
    padding = ROW_WIDTH * height - size
    if padding:
        values = np.pad(values, (0, padding), mode="constant", constant_values=fill)
    return values.reshape((height, ROW_WIDTH))


def build_binary_image(binary: bytes) -> Image.Image:
    array = np.frombuffer(binary, dtype=np.uint8)
    return Image.fromarray(reshape_bytes(array, 0xFF), mode="L")


def build_provenance_image(binary: bytes, indexes) -> Image.Image:
    """Blue-channel byte values with corrupted bytes marked in high-contrast red."""
    total = max(len(binary), max(indexes, default=-1) + 1)
    values = np.frombuffer(binary, dtype=np.uint8)
    if values.size < total:
        values = np.pad(values, (0, total - values.size), mode="constant", constant_values=0xFF)

    corrupted = np.zeros(total, dtype=bool)
    valid = [index for index in indexes if 0 <= index < total]
    corrupted[valid] = True
    missing = np.zeros(total, dtype=bool)
    missing[len(binary):] = True

    grid = reshape_bytes(values, 0xFF)
    corrupted_grid = reshape_bytes(corrupted, False)
    missing_grid = reshape_bytes(missing, False)

    rgb = np.zeros(grid.shape + (3,), dtype=np.uint8)
    rgb[:, :, 2] = grid
    rgb[missing_grid] = (255, 255, 0)
    rgb[corrupted_grid] = (255, 0, 0)
    return Image.fromarray(rgb, mode="RGB")


def build_mask_image(total: int, candidates) -> Image.Image:
    """Green where the strategy supplies a byte, red where it declines to repair."""
    repaired = np.zeros(total, dtype=bool)
    skipped = np.zeros(total, dtype=bool)
    for index, candidate in candidates:
        if not 0 <= index < total:
            continue
        if candidate == -1:
            skipped[index] = True
        else:
            repaired[index] = True

    repaired_grid = reshape_bytes(repaired, False)
    skipped_grid = reshape_bytes(skipped, False)

    rgb = np.full(repaired_grid.shape + (3,), 24, dtype=np.uint8)
    rgb[repaired_grid] = (0, 255, 0)
    rgb[skipped_grid] = (255, 0, 0)
    return Image.fromarray(rgb, mode="RGB")


def build_candidates(strategy, indexes, binary, isa, original_binary):
    """Return (index, candidate_byte) pairs for the selected repair strategy."""
    if strategy == "zero_fill":
        return [(index, 0 if 0 <= index < len(binary) else -1) for index in indexes]

    if strategy == "no_repair":
        return [(index, -1) for index in indexes]

    if strategy == "local_fill":
        candidates = local_fill.build_candidate_bytes(indexes, binary)
        return [(index, candidates[index]) for index in indexes]

    if strategy == "nop_fill":
        candidates = nop_fill.build_candidate_bytes(indexes, nop_fill.NOP_BYTES[isa])
        return [
            (index, candidates[index] if 0 <= index < len(binary) else -1)
            for index in indexes
        ]

    if strategy == "oracle_donor":
        return [
            (
                index,
                original_binary[index] if 0 <= index < len(original_binary) else -1,
            )
            for index in indexes
        ]

    raise ValueError(f"Unknown repair strategy: {strategy}")


def apply_candidates(binary: bytes, candidates) -> bytearray:
    """Apply candidates through the shared rewrite logic via a temporary repair CSV."""
    mended = bytearray(binary)
    with tempfile.TemporaryDirectory() as temp_dir:
        repair_csv = Path(temp_dir) / "gui.repair.csv"
        with repair_csv.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["index", "corrupted_byte", "candidate_byte"])
            for index, candidate in candidates:
                corrupted_byte = binary[index] if 0 <= index < len(binary) else -1
                writer.writerow([index, corrupted_byte, candidate])
        rewrite.apply_repairs(repair_csv, mended)
    return mended


class ImagePanel(ttk.Frame):
    def __init__(self, parent, title, caption):
        super().__init__(parent, padding=8)
        ttk.Label(self, text=title, font=("TkDefaultFont", 10, "bold")).pack()
        self.canvas = ttk.Label(self, relief="sunken", anchor="center")
        self.canvas.pack(fill="both", expand=True, pady=4)
        ttk.Label(self, text=caption, foreground="#555555").pack()
        self._photo = None
        self.image = None

    def show(self, image: Image.Image):
        self.image = image.copy()
        preview = image.copy()
        preview.thumbnail(PREVIEW_SIZE, Image.NEAREST)
        self._photo = ImageTk.PhotoImage(preview)
        self.canvas.configure(image=self._photo, text="")

    def clear(self, message="No data"):
        self._photo = None
        self.image = None
        self.canvas.configure(image="", text=message)


class HostGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FirmMend Host GUI")
        self.geometry("1200x680")

        self.binary_path = tk.StringVar()
        self.indexes_path = tk.StringVar()
        self.original_path = tk.StringVar()
        self.strategy = tk.StringVar(value=STRATEGIES[0])
        self.isa = tk.StringVar(value=sorted(nop_fill.NOP_BYTES)[0])
        self.status = tk.StringVar(value="Select a corrupted binary and an index CSV.")

        self.mended = None
        self._build_controls()
        self._build_panels()
        self._on_strategy_change()

    def _build_controls(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="x")

        self._file_row(frame, 0, "Corrupted binary", self.binary_path,
                       [("Binary files", "*.bin"), ("All files", "*.*")])
        self._file_row(frame, 1, "Corrupted byte indexes", self.indexes_path,
                       [("CSV files", "*.csv"), ("All files", "*.*")])
        self.original_row = self._file_row(
            frame, 2, "Original binary (oracle)", self.original_path,
            [("Binary files", "*.bin"), ("All files", "*.*")]
        )

        options = ttk.Frame(frame)
        options.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(options, text="Repair strategy").pack(side="left")
        strategy_box = ttk.Combobox(
            options, textvariable=self.strategy, values=STRATEGIES,
            state="readonly", width=18
        )
        strategy_box.pack(side="left", padx=8)
        strategy_box.bind("<<ComboboxSelected>>", lambda _event: self._on_strategy_change())

        self.isa_label = ttk.Label(options, text="ISA")
        self.isa_label.pack(side="left", padx=(12, 0))
        self.isa_box = ttk.Combobox(
            options, textvariable=self.isa, values=sorted(nop_fill.NOP_BYTES),
            state="readonly", width=12
        )
        self.isa_box.pack(side="left", padx=8)

        ttk.Button(options, text="Analyze", command=self.analyze).pack(side="left", padx=12)
        self.save_button = ttk.Button(
            options, text="Download mended binary", command=self.save_mended, state="disabled"
        )
        self.save_button.pack(side="left")
        self.save_images_button = ttk.Button(
            options, text="Save images as PDF", command=self.save_images_pdf, state="disabled"
        )
        self.save_images_button.pack(side="left", padx=(8, 0))

        frame.columnconfigure(1, weight=1)
        ttk.Label(self, textvariable=self.status, padding=(10, 0)).pack(fill="x")

    def _file_row(self, parent, row, label, variable, filetypes):
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=0, sticky="w", pady=2)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", padx=8, pady=2)
        button = ttk.Button(
            parent, text="Browse...",
            command=lambda: self._browse(variable, filetypes)
        )
        button.grid(row=row, column=2, pady=2)
        return (label_widget, entry, button)

    def _browse(self, variable, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            variable.set(path)

    def _build_panels(self):
        panels = ttk.Frame(self, padding=10)
        panels.pack(fill="both", expand=True)

        self.binary_panel = ImagePanel(
            panels, "Input binary", "Grayscale byte values, 512 bytes per row"
        )
        self.provenance_panel = ImagePanel(
            panels, "Corruption provenance", "Red = corrupted byte, yellow = missing tail"
        )
        self.mask_panel = ImagePanel(
            panels, "Repair mask", "Green = repaired, red = left unrepaired"
        )
        for column, panel in enumerate(
            (self.binary_panel, self.provenance_panel, self.mask_panel)
        ):
            panel.grid(row=0, column=column, sticky="nsew")
            panels.columnconfigure(column, weight=1)
        panels.rowconfigure(0, weight=1)

        for panel in (self.binary_panel, self.provenance_panel, self.mask_panel):
            panel.clear()

    def _on_strategy_change(self):
        needs_isa = self.strategy.get() == "nop_fill"
        needs_original = self.strategy.get() == "oracle_donor"
        self.isa_box.configure(state="readonly" if needs_isa else "disabled")
        for widget in self.original_row:
            widget.configure(state="normal" if needs_original else "disabled")

    def analyze(self):
        try:
            binary_path = Path(self.binary_path.get())
            indexes_path = Path(self.indexes_path.get())
            if not binary_path.is_file():
                raise ValueError("Select an existing corrupted binary file.")
            if not indexes_path.is_file():
                raise ValueError("Select an existing corrupted index CSV file.")

            binary = binary_path.read_bytes()
            indexes = load_indexes(indexes_path)
            if not indexes:
                raise ValueError("No corrupted byte indexes were found in the CSV file.")
            if any(index < 0 for index in indexes):
                raise ValueError("Corrupted byte indexes must be non-negative.")

            original_binary = b""
            if self.strategy.get() == "oracle_donor":
                original_path = Path(self.original_path.get())
                if not original_path.is_file():
                    raise ValueError("The oracle_donor strategy needs an original binary.")
                original_binary = original_path.read_bytes()

            candidates = build_candidates(
                self.strategy.get(), indexes, binary, self.isa.get(), original_binary
            )
            self.mended = apply_candidates(binary, candidates)

            total = max(len(self.mended), max(indexes) + 1)
            self.binary_panel.show(build_binary_image(binary))
            self.provenance_panel.show(build_provenance_image(binary, indexes))
            self.mask_panel.show(build_mask_image(total, candidates))

            repaired = sum(1 for _, candidate in candidates if candidate != -1)
            self.save_button.configure(state="normal")
            self.save_images_button.configure(state="normal")
            self.status.set(
                f"{len(indexes)} corrupted bytes, {repaired} repaired by "
                f"{self.strategy.get()}, mended size {len(self.mended)} bytes."
            )
        except Exception as error:  # surfaced to the user instead of the console
            self.mended = None
            self.save_button.configure(state="disabled")
            self.save_images_button.configure(state="disabled")
            self.status.set(str(error))
            messagebox.showerror("Analysis failed", str(error))

    def save_mended(self):
        if self.mended is None:
            return
        default_name = f"{Path(self.binary_path.get()).stem}.{self.strategy.get()}.mend.bin"
        path = filedialog.asksaveasfilename(
            defaultextension=".bin",
            initialfile=default_name,
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")],
        )
        if not path:
            return
        Path(path).write_bytes(bytes(self.mended))
        self.status.set(f"Saved mended binary to {path}")

    def save_images_pdf(self):
        images = [
            self.binary_panel.image,
            self.provenance_panel.image,
            self.mask_panel.image,
        ]
        if any(image is None for image in images):
            return
        default_name = f"{Path(self.binary_path.get()).stem}.{self.strategy.get()}.images.pdf"
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=default_name,
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        pdf_images = [image.convert("RGB") for image in images]
        pdf_images[0].save(path, "PDF", save_all=True, append_images=pdf_images[1:])
        self.status.set(f"Saved panel images to {path}")


def main():
    HostGui().mainloop()


if __name__ == "__main__":
    main()
