# Build from the repository root: docker build -f gui/Dockerfile -t firmmend-gui .
FROM python:3.8

# Tk runtime is required by the tkinter GUI.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tk libx11-6 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir numpy Pillow

WORKDIR /app
COPY src/ /app/src/
COPY gui/run.py /app/gui/run.py

RUN useradd --create-home firmmend
USER firmmend

ENTRYPOINT ["python", "/app/gui/run.py"]
