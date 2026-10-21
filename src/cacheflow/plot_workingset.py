"""Plot the 8-to-12 document working-set control at fixed GPU KV budget."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def summarize(raw: Path, config: dict[str, str]) -> dict:
    run = config["run_id"]
    req = rows(raw / f"{run}.jsonl")
    metrics = rows(raw / f"{run}.metrics.jsonl")
    summary = json.loads((raw / f"{run}.summary.json").read_text())
    groups = int(config["groups"])
    late = [x["arrival_ttft_ms"] for x in req if x["request_id"].endswith("q3")]
    if len(req) != 4 * groups or len(late) != groups or summary["successes"] != len(req):
        raise ValueError(f"incomplete run: {run}")
    a, b = metrics[0], metrics[-1]
    return {
        **config,
        "late_ttft_mean_ms": sum(late) / groups,
        "ttft_p50_ms": summary["arrival_ttft_p50_ms"],
        "output_tokens_per_s": summary["output_tokens_per_s"],
        "external_hit_tokens": b["vllm"].get("vllm:external_prefix_cache_hits_total", 0) - a["vllm"].get("vllm:external_prefix_cache_hits_total", 0),
        "computed_prefill_tokens": b["vllm"].get("vllm:request_prefill_kv_computed_tokens_sum", 0) - a["vllm"].get("vllm:request_prefill_kv_computed_tokens_sum", 0),
        "lmcache_loaded_chunks": b["lmcache"].get("lmcache_mp_num_chunks_loaded_total", 0) - a["lmcache"].get("lmcache_mp_num_chunks_loaded_total", 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--raw-dir", type=Path, default=Path("results/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/figures/workingset"))
    args = parser.parse_args()
    with args.matrix.open(newline="") as stream:
        data = [summarize(args.raw_dir, config) for config in csv.DictReader(stream)]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "workingset_metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    colors = {"B1": "#607d8b", "B2": "#f57c00"}
    for mode in ("B1", "B2"):
        for groups in (8, 12):
            selected = [x for x in data if x["mode"] == mode and int(x["groups"]) == groups]
            for i, x in enumerate(selected):
                xpos = groups + (-0.1 if mode == "B1" else 0.1) + (i - 0.5) * 0.035
                axes[0].scatter(xpos, x["late_ttft_mean_ms"], color=colors[mode], label=mode if groups == 8 and i == 0 else None)
                axes[1].scatter(xpos, x["external_hit_tokens"] / 1024, color=colors[mode], label=mode if groups == 8 and i == 0 else None)
    axes[0].set_ylabel("Late revisit TTFT mean (ms)")
    axes[1].set_ylabel("CPU tier hit tokens (thousands)")
    for ax in axes:
        ax.set_xticks([8, 12])
        ax.set_xlabel("Distinct 8K documents (GPU KV budget 8 GiB)")
        ax.grid(alpha=0.25)
        ax.legend()
    fig.savefig(args.output_dir / "workingset_pressure.png", dpi=180)
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
