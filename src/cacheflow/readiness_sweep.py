"""Observational producer first-token feasibility across wait bounds."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .diagnose_delay import diagnose

WINDOWS_MS = (50, 100, 200, 500, 1000, 1500, 2000, 2500)
GRACE_MS = 20


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--gateway", type=Path, default=Path("results/raw/gateway.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/figures/readiness"))
    args = parser.parse_args()
    with args.matrix.open(newline="") as stream:
        configs = list(csv.DictReader(stream))
    names = list(dict.fromkeys(row["label"] for row in configs))
    results = []
    for window in WINDOWS_MS:
        grouped = defaultdict(lambda: {"candidates": 0, "first_token_within": 0, "first_token_plus_grace_within": 0})
        for config in configs:
            label, run_id = config["label"], config["run_id"]
            first = diagnose(args.gateway, run_id, window)
            grace = diagnose(args.gateway, run_id, window - GRACE_MS)
            if first["candidates_with_matching_producer"] != grace["candidates_with_matching_producer"]:
                raise ValueError(f"inconsistent candidate matches for {run_id}")
            grouped[label]["candidates"] += first["candidates_with_matching_producer"]
            grouped[label]["first_token_within"] += first["producer_ready_within_wait_bound"]
            grouped[label]["first_token_plus_grace_within"] += grace["producer_ready_within_wait_bound"]
        for label in names:
            item = grouped[label]
            n = item["candidates"]
            results.append({"label": label, "window_ms": window, **item,
                            "first_token_fraction": item["first_token_within"] / n if n else None,
                            "first_token_plus_grace_fraction": item["first_token_plus_grace_within"] / n if n else None})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "readiness_windows.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    fig, ax = plt.subplots(figsize=(7.5, 4.5), constrained_layout=True)
    for label in names:
        selected = [row for row in results if row["label"] == label]
        ax.plot([row["window_ms"] for row in selected],
                [row["first_token_plus_grace_fraction"] for row in selected],
                marker="o", label=f"{label} (n={selected[0]['candidates']})")
    ax.axvline(200, color="#333333", linestyle="--", linewidth=1, label="tested bound 200 ms")
    ax.set(xlabel="Follower wait bound (ms)", ylabel="Observed producer first token + 20 ms within bound",
           xlim=(0, 2600), ylim=(-0.03, 1.03))
    ax.grid(alpha=0.25)
    ax.legend(loc="lower right")
    fig.savefig(args.output_dir / "readiness_feasibility.png", dpi=180)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
