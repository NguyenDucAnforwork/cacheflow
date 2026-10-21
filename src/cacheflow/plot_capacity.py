"""Summarize KV-budget sweep with per-run points and tier counters."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def row_metrics(root: Path, config: dict[str, str]) -> dict[str, float | str]:
    run_id = config["run_id"]
    requests = read_jsonl(root / f"{run_id}.jsonl")
    samples = read_jsonl(root / f"{run_id}.metrics.jsonl")
    summary = json.loads((root / f"{run_id}.summary.json").read_text())
    if len(requests) != 32 or summary["successes"] != 32:
        raise ValueError(f"incomplete run: {run_id}")
    if summary["trace_sha256"] != requests[0]["trace_sha256"]:
        raise ValueError(f"trace mismatch: {run_id}")
    late = [x["arrival_ttft_ms"] for x in requests if x["request_id"].endswith("q3")]
    if len(late) != 8:
        raise ValueError(f"expected eight late revisits: {run_id}")
    first, last = samples[0], samples[-1]
    def delta(section: str, key: str) -> float:
        return last[section].get(key, 0.0) - first[section].get(key, 0.0)
    return {
        **config,
        "gpu_kv_gib": int(config["gpu_kv_bytes"]) / 2**30,
        "ttft_p50_ms": summary["arrival_ttft_p50_ms"],
        "late_ttft_mean_ms": sum(late) / 8,
        "output_tokens_per_s": summary["output_tokens_per_s"],
        "external_hit_tokens": delta("vllm", "vllm:external_prefix_cache_hits_total"),
        "gpu_hit_tokens": delta("vllm", "vllm:prefix_cache_hits_total"),
        "computed_prefill_tokens": delta("vllm", "vllm:request_prefill_kv_computed_tokens_sum"),
        "lmcache_loaded_chunks": delta("lmcache", "lmcache_mp_num_chunks_loaded_total"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--raw-dir", type=Path, default=Path("results/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/figures/capacity"))
    args = parser.parse_args()
    with args.matrix.open(newline="") as stream:
        rows = [row_metrics(args.raw_dir, x) for x in csv.DictReader(stream)]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "capacity_metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    colors = {"B1": "#607d8b", "B2": "#f57c00"}
    for mode in ("B1", "B2"):
        selected = [x for x in rows if x["mode"] == mode]
        for budget in sorted({x["gpu_kv_gib"] for x in selected}):
            matching = [x for x in selected if x["gpu_kv_gib"] == budget]
            for i, x in enumerate(matching):
                offset = (-0.08 if mode == "B1" else 0.08) + (i - (len(matching)-1)/2)*0.025
                axes[0].scatter(budget + offset, x["late_ttft_mean_ms"], color=colors[mode], marker="o", label=mode if budget == 4 and i == 0 else None)
                axes[1].scatter(budget + offset, x["external_hit_tokens"] / 1024, color=colors[mode], marker="o", label=mode if budget == 4 and i == 0 else None)
    axes[0].set_ylabel("Late revisit TTFT mean (ms)")
    axes[1].set_ylabel("CPU tier hit tokens (thousands)")
    for ax in axes:
        ax.set_xticks(sorted({x["gpu_kv_gib"] for x in rows}))
        ax.set_xlabel("GPU KV budget (GiB)")
        ax.grid(alpha=0.25)
        ax.legend()
    fig.savefig(args.output_dir / "capacity_boundary.png", dpi=180)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
