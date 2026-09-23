# FirmMend Host GUI

A Tk desktop tool that loads a corrupted firmware binary plus a list of corrupted byte
indexes, visualizes the corruption, applies a repair strategy, and exports the mended
binary.

## What it shows

| Panel | Meaning |
| --- | --- |
| Input binary | Grayscale pixel art of the raw bytes, 512 bytes per row |
| Corruption provenance | Byte values in the blue channel, corrupted bytes in pure red, missing tail bytes in yellow |
| Repair mask | Green where the selected strategy supplies a byte, red where it declines to repair |

## Inputs

- **Corrupted binary** — a `.bin` file.
- **Corrupted byte indexes** — a CSV whose first column holds byte offsets, with or
  without a header (the `*.indexes.csv` files produced by `src/util/diff.py` work as-is).
- **Repair strategy** — `zero_fill`, `nop_fill` (requires an ISA), `local_fill`,
  `oracle_donor` (requires the original binary), or `no_repair`.

Click **Analyze** to render the panels. **Download mended binary** saves the result
as `<stem>.<strategy>.mend.bin`; **Save images as PDF** saves the three full-resolution
panels as a multi-page PDF.

## Run locally

Requires Python 3.9+ with Tk support, `numpy`, and `Pillow`.

```bash
pip install numpy Pillow
python gui/run.py
```

On Debian/Ubuntu, install Tk first with `sudo apt-get install python3-tk`.

## Build the Docker image

The image needs `src/` as well as `gui/`, so build from the repository root and point
Docker at the Dockerfile inside `gui/`:

```bash
cd /path/to/firmmend
docker build -f gui/Dockerfile -t firmmend-gui .
```

## Run the dockerized GUI

The container runs a desktop application, so it needs access to an X display. Mount a
host directory to `/data` so the file dialogs can read your binaries and write the
mended output back to the host.

### Linux

```bash
xhost +local:docker
docker run --rm \
  -e DISPLAY="$DISPLAY" \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v "$PWD/demo:/data" \
  firmmend-gui
xhost -local:docker
```

### macOS (XQuartz)

Enable *Allow connections from network clients* in XQuartz preferences, restart
XQuartz, then:

```bash
xhost + 127.0.0.1
docker run --rm \
  -e DISPLAY=host.docker.internal:0 \
  -v "$PWD/demo:/data" \
  firmmend-gui
```

### Windows with WSL2 + WSLg

Run the Docker command from inside a WSL2 shell:

```bash
docker run --rm \
  -e DISPLAY="$DISPLAY" \
  -e WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
  -e XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v /mnt/wslg:/mnt/wslg \
  -v "$PWD/demo:/data" \
  firmmend-gui
```

### Windows with VcXsrv

Start VcXsrv with *Disable access control* checked, then from PowerShell:

```powershell
docker run --rm `
  -e DISPLAY=host.docker.internal:0.0 `
  -v "${PWD}\demo:/data" `
  firmmend-gui
```

## Troubleshooting

- `couldn't connect to display` — the `DISPLAY` value is wrong or the X server is not
  accepting connections; re-check the `xhost` step for your platform.
- `no module named tkinter` when running locally — install your distribution's
  `python3-tk` package.
- Saved files are missing on the host — save into `/data`, which is the mounted host
  directory; anything written elsewhere disappears when the container exits.
- Permission denied writing to `/data` — the container runs as the non-root `firmmend`
  user; make the mounted directory writable, or add `--user "$(id -u):$(id -g)"`.
