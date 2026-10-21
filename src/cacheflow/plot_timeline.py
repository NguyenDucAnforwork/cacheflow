"""Plot client-visible request phases and sampled CPU-tier reads for one run."""

from __future__ import annotations

import argparse
from pathlib import Path

from cacheflow.analyze import read_jsonl


def plot(run_path: Path, output: Path, group: str | None = None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = read_jsonl(run_path)
    if not rows:
        raise ValueError("empty benchmark run")
    group = group or sorted({row["group"] for row in rows})[0]
    selected = sorted((row for row in rows if row["group"] == group),
                      key=lambda row: row["scheduled_arrival_ns"])
    if not selected:
        raise ValueError(f"group {group!r} is absent")
    epoch = min(row["scheduled_arrival_ns"] for row in rows)
    gateway_path = run_path.parent / "gateway.jsonl"
    gateway = {(row["run_id"], row["request_id"]): row for row in read_jsonl(gateway_path)
               if "run_id" in row and "request_id" in row}
    if any((row["run_id"], row["request_id"]) not in gateway for row in selected):
        raise ValueError("gateway timing records are missing for the selected group")
    metric_path = run_path.with_suffix(".metrics.jsonl")
    metrics = read_jsonl(metric_path) if metric_path.exists() else []
    previous_reads = 0.0

    fig, ax = plt.subplots(figsize=(11, max(3.3, len(selected) * 0.7 + 1.5)))
    colors = {"arrival to dispatch": "tab:gray", "dispatch to first token": "tab:orange",
              "first token to completion": "tab:green"}
    for index, row in enumerate(selected):
        dispatch = gateway[(row["run_id"], row["request_id"])]["dispatch_ns"]
        intervals = (("arrival to dispatch", row["scheduled_arrival_ns"], dispatch),
                     ("dispatch to first token", dispatch, row["first_token_ns"]),
                     ("first token to completion", row["first_token_ns"], row["complete_ns"]))
        for label, start, end in intervals:
            ax.barh(index, max(0, end - start) / 1e9, left=(start - epoch) / 1e9,
                    height=0.55, color=colors[label], label=label if index == 0 else None)

    labeled_read = False
    for sample in metrics:
        reads = sample.get("lmcache", {}).get("lmcache_mp_l1_read_chunks_total", previous_reads)
        if reads > previous_reads:
            ax.axvline((sample["timestamp_ns"] - epoch) / 1e9, color="tab:blue",
                       linestyle=":", alpha=0.55, label="sampled L1 read increase" if not labeled_read else None)
            labeled_read = True
        previous_reads = reads
    ax.set_yticks(range(len(selected)), [row["request_id"] for row in selected])
    ax.invert_yaxis()
    ax.set(xlabel="Seconds from first scheduled request in run", title=f"{run_path.stem}: {group} request phases")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--group")
    args = parser.parse_args()
    plot(args.run, args.output, args.group)


if __name__ == "__main__":
    main()
