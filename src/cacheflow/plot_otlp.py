"""Plot LMCache MP operation intervals from the separate OTLP profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def plot(source: Path, output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    if not rows:
        raise ValueError("empty OTLP capture")
    origin = min(row["start_time_unix_nano"] for row in rows)
    series = (
        ("mp.lookup_prefetch", "Lookup/prefetch", "tab:orange"),
        ("mp.store", "Store", "tab:green"),
        ("mp.retrieve", "CPU KV retrieve", "tab:blue"),
    )
    fig, ax = plt.subplots(figsize=(11, 4))
    for y, (name, label, color) in enumerate(series):
        for row in (row for row in rows if row["name"] == name):
            start = (row["start_time_unix_nano"] - origin) / 1e9
            duration = max(0, row["end_time_unix_nano"] - row["start_time_unix_nano"]) / 1e9
            ax.broken_barh([(start, duration)], (y - 0.32, 0.64), facecolors=color, alpha=0.72)
    ax.set_yticks(range(len(series)), [label for _, label, _ in series])
    ax.set(xlabel="Seconds from first captured LMCache operation",
           title="LMCache MP operations in a separate 8K revisit profile")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    plot(args.source, args.output)


if __name__ == "__main__":
    main()
