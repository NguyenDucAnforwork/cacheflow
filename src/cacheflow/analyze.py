"""Paired, request-level analysis of CacheFlow experiment runs."""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct / 100
    lo = int(position)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def metric_delta(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    samples = read_jsonl(path)
    if len(samples) < 2:
        return {}
    first, last = samples[0], samples[-1]
    output = {}
    for tier in ("vllm", "lmcache"):
        for name, value in last.get(tier, {}).items():
            old = first.get(tier, {}).get(name, 0)
            if isinstance(value, (float, int)) and isinstance(old, (float, int)):
                output[name] = value - old
    return output


def resource_summary(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    samples = read_jsonl(path)
    if not samples:
        return {}
    def values(*keys: str) -> list[float]:
        output = []
        for row in samples:
            value = row
            for key in keys:
                value = value.get(key) if isinstance(value, dict) else None
            if isinstance(value, (int, float)):
                output.append(float(value))
        return output

    summary = {}
    for label, keys, reduction in (
        ("host_cpu_mean_pct", ("cpu_percent",), statistics.mean),
        ("gpu_sm_mean_pct", ("gpu", "gpu_util_pct"), statistics.mean),
        ("gpu_sm_clock_mean_mhz", ("gpu", "sm_clock_mhz"), statistics.mean),
        ("gpu_temperature_peak_c", ("gpu", "temperature_c"), max),
        ("gpu_power_mean_w", ("gpu", "power_w"), statistics.mean),
        ("vram_peak_mib", ("gpu", "vram_used_mib"), max),
        ("host_ram_available_min_gib", ("memory_available_bytes",), min),
        ("gpu_kv_usage_peak_fraction", ("vllm", "vllm:kv_cache_usage_perc"), max),
        ("cpu_l1_peak_gib", ("lmcache", "lmcache_mp_l1_memory_usage_bytes"), max),
    ):
        series = values(*keys)
        if series:
            value = reduction(series)
            if label.endswith("_gib"):
                value /= 1024 ** 3
            summary[label] = value
    for process in ("gateway", "vllm", "lmcache"):
        series = values("process", process, "cpu_seconds")
        if len(series) > 1:
            summary[f"{process}_cpu_seconds_delta"] = max(0.0, series[-1] - series[0])
        series = values("process", process, "rss_bytes")
        if series:
            summary[f"{process}_rss_peak_gib"] = max(series) / 1024 ** 3
    return summary


def compare(a_path: Path, b_path: Path) -> dict:
    a_rows, b_rows = read_jsonl(a_path), read_jsonl(b_path)
    a = {r["request_id"]: r for r in a_rows}
    b = {r["request_id"]: r for r in b_rows}
    if set(a) != set(b):
        raise ValueError("request IDs differ between arms")
    hashes = {r["trace_sha256"] for r in a_rows + b_rows}
    if len(hashes) != 1:
        raise ValueError("trace hashes differ between arms")
    if any(a[k]["prompt_sha256"] != b[k]["prompt_sha256"] or a[k]["input_tokens"] != b[k]["input_tokens"] for k in a):
        raise ValueError("prompt content or token counts differ between arms")
    comparable = [k for k in sorted(a) if a[k]["status"] == b[k]["status"] == "ok"
                  and a[k]["arrival_ttft_ms"] is not None and b[k]["arrival_ttft_ms"] is not None]
    deltas = [b[k]["arrival_ttft_ms"] - a[k]["arrival_ttft_ms"] for k in comparable]
    by_group = defaultdict(list)
    for k in comparable:
        by_group[a[k]["group"]].append(b[k]["arrival_ttft_ms"] - a[k]["arrival_ttft_ms"])
    rng = random.Random(7)
    groups = sorted(by_group)
    bootstrap = []
    if groups:
        for _ in range(2000):
            sampled = [rng.choice(groups) for _ in groups]
            values = [x for group in sampled for x in by_group[group]]
            bootstrap.append(statistics.mean(values))
    a_ttft = [a[k]["arrival_ttft_ms"] for k in comparable]
    b_ttft = [b[k]["arrival_ttft_ms"] for k in comparable]
    a_summary = json.loads(a_path.with_suffix(".summary.json").read_text())
    b_summary = json.loads(b_path.with_suffix(".summary.json").read_text())
    a_metrics = metric_delta(a_path.with_suffix(".metrics.jsonl"))
    b_metrics = metric_delta(b_path.with_suffix(".metrics.jsonl"))
    a_resources = resource_summary(a_path.with_suffix(".metrics.jsonl"))
    b_resources = resource_summary(b_path.with_suffix(".metrics.jsonl"))
    return {
        "a_run_id": a_summary["run_id"], "b_run_id": b_summary["run_id"],
        "trace_sha256": hashes.pop(), "paired_count": len(comparable), "request_count": len(a),
        "a_errors": sum(r["status"] != "ok" for r in a_rows),
        "b_errors": sum(r["status"] != "ok" for r in b_rows),
        "output_hash_mismatches": sum(a[k]["output_hash"] != b[k]["output_hash"] for k in comparable),
        "a_ttft_p50_ms": percentile(a_ttft, 50), "a_ttft_p90_ms": percentile(a_ttft, 90),
        "b_ttft_p50_ms": percentile(b_ttft, 50), "b_ttft_p90_ms": percentile(b_ttft, 90),
        "paired_ttft_mean_delta_ms": statistics.mean(deltas) if deltas else None,
        "paired_ttft_median_delta_ms": percentile(deltas, 50),
        "paired_mean_delta_cluster_bootstrap_95_ms": [percentile(bootstrap, 2.5), percentile(bootstrap, 97.5)] if bootstrap else None,
        "a_output_tokens_per_s": a_summary["output_tokens_per_s"],
        "b_output_tokens_per_s": b_summary["output_tokens_per_s"],
        "a_cache_metric_deltas": a_metrics, "b_cache_metric_deltas": b_metrics,
        "a_resource_summary": a_resources, "b_resource_summary": b_resources,
    }


def figures(a_path: Path, b_path: Path, output_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    a = {r["request_id"]: r for r in read_jsonl(a_path)}
    b = {r["request_id"]: r for r in read_jsonl(b_path)}
    a_info = json.loads(a_path.with_suffix(".summary.json").read_text())
    b_info = json.loads(b_path.with_suffix(".summary.json").read_text())
    a_label = f"{a_info['mode']} {a_info['policy']}"
    b_label = f"{b_info['mode']} {b_info['policy']}"
    keys = [k for k in sorted(a) if a[k]["arrival_ttft_ms"] and b[k]["arrival_ttft_ms"]]
    xs = [a[k]["arrival_ttft_ms"] for k in keys]
    ys = [b[k]["arrival_ttft_ms"] for k in keys]
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(xs, ys, alpha=0.75, s=28)
    lim = max(xs + ys, default=1) * 1.05
    ax.plot([0, lim], [0, lim], color="gray", linestyle="--", linewidth=1)
    ax.set(xlabel=f"{a_label} arrival TTFT (ms)", ylabel=f"{b_label} arrival TTFT (ms)", title="Paired requests")
    fig.tight_layout()
    fig.savefig(output_dir / "paired_ttft.png", dpi=160)
    plt.close(fig)

    metrics = read_jsonl(b_path.with_suffix(".metrics.jsonl")) if b_path.with_suffix(".metrics.jsonl").exists() else []
    if metrics:
        first = metrics[0]["timestamp_ns"]
        seconds = [(row["timestamp_ns"] - first) / 1e9 for row in metrics]
        cpu = [row.get("cpu_percent", 0) for row in metrics]
        gpu = [row.get("gpu", {}).get("gpu_util_pct", 0) for row in metrics]
        reads = [row.get("lmcache", {}).get("lmcache_mp_l1_read_chunks_total", 0) for row in metrics]
        read_deltas = [0] + [max(0, current - previous) for previous, current in zip(reads, reads[1:])]
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(seconds, gpu, label="GPU SM utilization (%)")
        ax.plot(seconds, cpu, label="Host CPU utilization (%)", alpha=0.7)
        ax.set(xlabel="Seconds from first sample", ylabel="Utilization (%)", title=f"Host and GPU activity during {b_label} run")
        secondary = ax.twinx()
        secondary.bar(seconds, read_deltas, width=0.6, color="tab:green", alpha=0.22, label="LMCache L1 read chunks")
        secondary.set_ylabel("L1 read chunks / sample")
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = secondary.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, loc="upper right")
        fig.tight_layout()
        fig.savefig(output_dir / "cpu_gpu_timeline.png", dpi=160)
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("a", type=Path, help="first run JSONL")
    parser.add_argument("b", type=Path, help="second run JSONL")
    parser.add_argument("--output-dir", type=Path, default=Path("/workspace/results/figures"))
    args = parser.parse_args()
    result = compare(args.a, args.b)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f"{result['a_run_id']}_vs_{result['b_run_id']}.json"
    path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    figures(args.a, args.b, args.output_dir)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
