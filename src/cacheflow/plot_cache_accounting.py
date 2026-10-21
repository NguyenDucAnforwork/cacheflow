"""Plot computed versus GPU- and CPU-reused prompt tokens on one trace."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def read_metrics(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def summarize(raw: Path, config: dict[str, str]) -> dict:
    run_id = config["run_id"]
    summary = json.loads((raw / f"{run_id}.summary.json").read_text())
    samples = read_metrics(raw / f"{run_id}.metrics.jsonl")
    first, last = samples[0]["vllm"], samples[-1]["vllm"]
    def delta(name: str) -> int:
        return int(last.get(name, 0) - first.get(name, 0))
    computed = delta("vllm:request_prefill_kv_computed_tokens_sum")
    gpu = delta("vllm:prefix_cache_hits_total")
    cpu = delta("vllm:external_prefix_cache_hits_total")
    prompt = delta("vllm:prompt_tokens_total")
    if computed + gpu + cpu != prompt:
        raise ValueError(f"token accounting mismatch in {run_id}: {computed}+{gpu}+{cpu}!={prompt}")
    return {**config, "trace_sha256": summary["trace_sha256"], "prompt_tokens": prompt,
            "computed_tokens": computed, "gpu_hit_tokens": gpu, "cpu_hit_tokens": cpu,
            "arrival_ttft_p50_ms": summary["arrival_ttft_p50_ms"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--raw-dir", type=Path, default=Path("results/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/figures/cache_accounting"))
    args = parser.parse_args()
    with args.matrix.open(newline="") as stream:
        data = [summarize(args.raw_dir, row) for row in csv.DictReader(stream)]
    if len({row["trace_sha256"] for row in data}) != 1:
        raise ValueError("matrix mixes workload traces")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "cache_accounting.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)
    labels = [row["label"] for row in data]
    fig, ax = plt.subplots(figsize=(8, 4.2), constrained_layout=True)
    bottom = [0] * len(data)
    for key, label, color in [
        ("computed_tokens", "New prefill", "#6d4c41"),
        ("gpu_hit_tokens", "GPU KV hit", "#607d8b"),
        ("cpu_hit_tokens", "CPU KV restore", "#f57c00"),
    ]:
        values = [row[key] / 1000 for row in data]
        ax.bar(labels, values, bottom=bottom, label=label, color=color)
        bottom = [a + b for a, b in zip(bottom, values)]
    ax.set_ylabel("Prompt tokens (thousands)")
    ax.set_title("8K document revisit · 32 requests · same trace")
    ax.legend(loc="lower left")
    ax.grid(axis="y", alpha=0.2)
    ax.set_axisbelow(True)
    fig.savefig(args.output_dir / "cache_accounting.png", dpi=180)
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
