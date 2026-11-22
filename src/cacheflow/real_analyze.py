"""Per-class latency, SLO attainment, goodput, cache accounting and answer-quality analysis for real-data runs."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

from .analyze import metric_delta, percentile, read_jsonl, resource_summary

SLO_TTFT_MS = {"chat": 1000.0, "doc": 3000.0}
SLO_TPOT_MS = 100.0
CONFIG_ORDER = ["B1", "B2", "B2T"]
COLORS = {"B1": "#0072B2", "B2": "#E69F00", "B2T": "#009E73"}
LETTER = re.compile(r"\b([ABCD])\b")


def parse_run_id(run_id: str) -> tuple[str, str, str]:
    _, trace, config, tag = run_id.split("-", 3)
    return trace, config.upper(), tag


def _meets_slo(record: dict) -> bool:
    if record["status"] != "ok" or record["arrival_ttft_ms"] is None:
        return False
    if record["arrival_ttft_ms"] > SLO_TTFT_MS[record["cls"]]:
        return False
    tpot = record.get("tpot_ms")  # undefined for <=1 output token: the TPOT target is vacuous there
    return tpot is None or tpot <= SLO_TPOT_MS


def _gateway_index(path: Path, run_ids: set[str]) -> dict[tuple[str, str], dict]:
    index = {}
    if path.exists():
        with path.open(encoding="utf-8") as file:
            for line in file:
                if '"run_id"' in line and any(f'"{rid}"' in line for rid in run_ids):
                    row = json.loads(line)
                    index[(row["run_id"], row["request_id"])] = row
    return index


def _class_stats(records: list[dict], gateway: dict, run_id: str, duration_s: float) -> dict:
    ttft = [r["arrival_ttft_ms"] for r in records if r["status"] == "ok" and r["arrival_ttft_ms"] is not None]
    tpot = [r["tpot_ms"] for r in records if r["status"] == "ok" and r["tpot_ms"] is not None]
    queue = [gateway[(run_id, r["request_id"])]["queue_wait_ms"] for r in records
             if (run_id, r["request_id"]) in gateway and gateway[(run_id, r["request_id"])].get("queue_wait_ms") is not None]
    good = sum(_meets_slo(r) for r in records)
    outs = [r["output_tokens"] for r in records if r["status"] == "ok"]
    n = len(records)
    return {
        "n": n, "completed": sum(r["status"] == "ok" for r in records), "errors": sum(r["status"] != "ok" for r in records),
        "completion_rate": sum(r["status"] == "ok" for r in records) / n if n else None,
        "ttft_p50_ms": percentile(ttft, 50), "ttft_p95_ms": percentile(ttft, 95), "n_ttft": len(ttft),
        "tpot_p50_ms": percentile(tpot, 50), "tpot_p95_ms": percentile(tpot, 95), "n_tpot": len(tpot),
        "output_tokens_total": sum(outs), "output_tokens_mean": statistics.mean(outs) if outs else None,
        "slo_attainment": good / n if n else None, "slo_good": good, "goodput_req_per_s": good / duration_s,
        "gateway_queue_wait_p50_ms": percentile(queue, 50), "gateway_queue_wait_p95_ms": percentile(queue, 95),
        "request_throughput_per_s": sum(r["status"] == "ok" for r in records) / duration_s,
    }


def _accuracy(outputs: list[dict]) -> dict:
    docs = [o for o in outputs if o["cls"] == "doc"]
    correct = 0
    answered = 0
    for item in docs:
        match = LETTER.search(item["output_text"])
        if match:
            answered += 1
            correct += match.group(1) == item["gold_letter"]
    return {"doc_n": len(docs), "answered": answered, "correct": correct, "accuracy": correct / len(docs) if docs else None}


def analyze_run(run_id: str, raw_dir: Path, gateway: dict) -> dict:
    path = raw_dir / f"{run_id}.jsonl"
    records = read_jsonl(path)
    summary = json.loads((raw_dir / f"{run_id}.summary.json").read_text())
    outputs = read_jsonl(raw_dir / f"{run_id}.outputs.jsonl")
    start = min(r["scheduled_arrival_ns"] for r in records)
    duration_s = (max(r["complete_ns"] for r in records) - start) / 1e9
    by_cls = {cls: [r for r in records if r["cls"] == cls] for cls in ("chat", "doc")}
    trace, config, tag = parse_run_id(run_id)
    delta = metric_delta(raw_dir / f"{run_id}.metrics.jsonl")
    gpu_hit = delta.get("vllm:prefix_cache_hits_total", 0.0)
    cpu_hit = delta.get("vllm:external_prefix_cache_hits_total", 0.0)
    computed = delta.get("vllm:request_prefill_kv_computed_tokens_sum", 0.0)
    all_stats = _class_stats(records, gateway, run_id, duration_s)
    outs = sum(r["output_tokens"] for r in records)
    return {
        "run_id": run_id, "trace": trace, "config": config, "tag": tag, "trace_sha256": summary["trace_sha256"],
        "git_sha": summary["git_sha"], "duration_s": duration_s, "requests": len(records),
        "output_tokens_total": outs, "output_tokens_per_s": outs / duration_s,
        "classes": {cls: _class_stats(rows, gateway, run_id, duration_s) for cls, rows in by_cls.items()},
        "overall": all_stats,
        "cache_tokens": {"gpu_hit": gpu_hit, "cpu_hit": cpu_hit, "computed_prefill": computed,
                         "prompt_total": delta.get("vllm:prompt_tokens_total", 0.0),
                         "cpu_chunks_loaded": delta.get("lmcache_mp_num_chunks_loaded_total", 0.0)},
        "vllm_engine_queue_time_mean_s": (delta.get("vllm:request_queue_time_seconds_sum", 0.0) / delta["vllm:request_queue_time_seconds_count"])
        if delta.get("vllm:request_queue_time_seconds_count") else None,
        "resources": resource_summary(raw_dir / f"{run_id}.metrics.jsonl"),
        "engine": {k: v for k, v in summary.items() if k.startswith(("engine_", "max_num_batched", "gpu_kv"))},
        "quality": _accuracy(outputs), "output_hashes": {o["request_id"]: o["output_text"] for o in outputs},
    }


def _mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def aggregate(runs: list[dict]) -> dict:
    groups = defaultdict(list)
    for run in runs:
        groups[(run["trace"], run["config"])].append(run)
    table = {}
    for (trace, config), items in groups.items():
        entry = {"runs": [i["run_id"] for i in items], "n_runs": len(items)}
        for cls in ("chat", "doc"):
            entry[cls] = {key: _mean([i["classes"][cls][key] for i in items]) for key in items[0]["classes"][cls]}
            entry[cls]["ttft_p95_ms_runs"] = [i["classes"][cls]["ttft_p95_ms"] for i in items]
        entry["goodput_req_per_s"] = _mean([i["overall"]["goodput_req_per_s"] for i in items])
        entry["slo_attainment_all"] = _mean([i["overall"]["slo_attainment"] for i in items])
        entry["request_throughput_per_s"] = _mean([i["requests"] / i["duration_s"] for i in items])
        entry["output_tokens_per_s"] = _mean([i["output_tokens_per_s"] for i in items])
        entry["duration_s"] = _mean([i["duration_s"] for i in items])
        entry["cache_tokens"] = {k: _mean([i["cache_tokens"][k] for i in items]) for k in items[0]["cache_tokens"]}
        entry["gpu_sm_mean_pct"] = _mean([i["resources"].get("gpu_sm_mean_pct") for i in items])
        entry["vram_peak_mib"] = max(i["resources"].get("vram_peak_mib", 0) for i in items)
        entry["cpu_l1_peak_gib"] = max(i["resources"].get("cpu_l1_peak_gib", 0) for i in items)
        entry["host_ram_available_min_gib"] = min(i["resources"].get("host_ram_available_min_gib", 1e9) for i in items)
        entry["vllm_engine_queue_time_mean_s"] = _mean([i["vllm_engine_queue_time_mean_s"] for i in items])
        entry["doc_accuracy"] = _mean([i["quality"]["accuracy"] for i in items])
        entry["engine"] = items[0]["engine"]
        table[f"{trace}/{config}"] = entry
    return table


def output_differences(runs: list[dict]) -> list[dict]:
    """Per trace, compare every run's output text with the first B1 run (same prompts, temperature 0)."""
    result = []
    for trace in sorted({r["trace"] for r in runs}):
        trace_runs = sorted((r for r in runs if r["trace"] == trace), key=lambda r: (CONFIG_ORDER.index(r["config"]), r["tag"]))
        ref = next((r for r in trace_runs if r["config"] == "B1"), None)
        if ref is None:
            continue
        for run in trace_runs:
            if run is ref:
                continue
            common = set(run["output_hashes"]) & set(ref["output_hashes"])
            diff = [rid for rid in common if run["output_hashes"][rid] != ref["output_hashes"][rid]]
            letters = [rid for rid in diff if rid.startswith("doc") and
                       (LETTER.search(run["output_hashes"][rid]) or [None, None])[1] != (LETTER.search(ref["output_hashes"][rid]) or [None, None])[1]]
            result.append({"trace": trace, "run": run["run_id"], "reference": ref["run_id"], "requests_compared": len(common),
                           "output_text_differs": len(diff), "doc_answer_letter_differs": len(letters)})
    return result


def make_figures(table: dict, out_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    traces = sorted({k.split("/")[0] for k in table})
    configs = [c for c in CONFIG_ORDER if any(k.endswith("/" + c) for k in table)]

    fig, axes = plt.subplots(len(traces), 2, figsize=(10, 3.6 * len(traces)), squeeze=False, constrained_layout=True)
    for row, trace in enumerate(traces):
        for col, cls in enumerate(("chat", "doc")):
            ax = axes[row][col]
            width = 0.35
            for i, config in enumerate(configs):
                entry = table.get(f"{trace}/{config}")
                if not entry:
                    continue
                for j, (key, hatch) in enumerate((("ttft_p50_ms", None), ("ttft_p95_ms", "//"))):
                    ax.bar(i + (j - 0.5) * width, entry[cls][key] / 1000, width, color=COLORS[config], hatch=hatch, edgecolor="white")
            ax.axhline(SLO_TTFT_MS[cls] / 1000, color="#444", linestyle="--", linewidth=1)
            ax.set_xticks(range(len(configs)), configs)
            ax.set_title(f"{trace}: {cls} TTFT (solid p50, hatched p95; dashed SLO {SLO_TTFT_MS[cls] / 1000:.0f}s)", fontsize=9)
            ax.set_ylabel("arrival TTFT (s)")
    fig.savefig(out_dir / "per_class_latency.png", dpi=140)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), constrained_layout=True)
    labels, keys = [], []
    for trace in traces:
        for config in configs:
            if f"{trace}/{config}" in table:
                keys.append(f"{trace}/{config}")
                labels.append(f"{trace[5:] if trace.startswith('real_') else trace}\n{config}")
    for k, key in enumerate(keys):
        entry = table[key]
        config = key.split("/")[1]
        bottom = 0.0
        for cls, hatch in (("chat", None), ("doc", "//")):
            value = entry[cls]["goodput_req_per_s"]
            axes[0].bar(k, value, bottom=bottom, color=COLORS[config], hatch=hatch, edgecolor="white")
            bottom += value
        axes[1].bar(k, entry["output_tokens_per_s"], color=COLORS[config], edgecolor="white")
    axes[0].set_xticks(range(len(keys)), labels, fontsize=8)
    axes[1].set_xticks(range(len(keys)), labels, fontsize=8)
    axes[0].set_title("Goodput (req/s meeting both SLOs; solid chat, hatched doc)", fontsize=9)
    axes[1].set_title("Output throughput (tokens/s)", fontsize=9)
    fig.savefig(out_dir / "goodput_throughput.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 3.8), constrained_layout=True)
    for k, key in enumerate(keys):
        tokens = table[key]["cache_tokens"]
        bottom = 0.0
        for name, color in (("gpu_hit", "#0072B2"), ("cpu_hit", "#E69F00"), ("computed_prefill", "#999999")):
            ax.bar(k, tokens[name] / 1000, bottom=bottom, color=color, edgecolor="white", label=name if k == 0 else None)
            bottom += tokens[name] / 1000
    ax.set_xticks(range(len(keys)), labels, fontsize=8)
    ax.set_ylabel("prompt tokens (thousands)")
    ax.set_title("Prompt-token source: GPU prefix hit / CPU (LMCache) restore / newly computed", fontsize=9)
    ax.legend(fontsize=8)
    fig.savefig(out_dir / "kv_cache_accounting.png", dpi=140)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="results/real_registry.csv")
    parser.add_argument("--raw-dir", default="results/raw")
    parser.add_argument("--gateway", default="results/raw/gateway.jsonl")
    parser.add_argument("--out-dir", default="results/figures/real_workload")
    parser.add_argument("--summary-json", default="results/real/analysis.json")
    args = parser.parse_args()
    with open(args.registry, newline="") as file:
        run_ids = [row["run_id"] for row in csv.DictReader(file)]
    gateway = _gateway_index(Path(args.gateway), set(run_ids))
    runs = [analyze_run(rid, Path(args.raw_dir), gateway) for rid in run_ids]
    table = aggregate(runs)
    for run in runs:
        run.pop("output_hashes")
    diffs = output_differences([analyze_run(rid, Path(args.raw_dir), gateway) for rid in run_ids])
    Path(args.summary_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary_json).write_text(json.dumps({"slo": {"ttft_ms": SLO_TTFT_MS, "tpot_ms": SLO_TPOT_MS}, "runs": runs,
                                                   "aggregate": table, "output_differences": diffs}, indent=1, sort_keys=True) + "\n")
    make_figures(table, Path(args.out_dir))
    for key, entry in sorted(table.items()):
        print(key, f"n_runs={entry['n_runs']}",
              f"chat p95={entry['chat']['ttft_p95_ms']:.0f}ms slo={entry['chat']['slo_attainment']:.2f}",
              f"doc p95={entry['doc']['ttft_p95_ms']:.0f}ms slo={entry['doc']['slo_attainment']:.2f}",
              f"goodput={entry['goodput_req_per_s']:.2f}/s tok/s={entry['output_tokens_per_s']:.0f}")


if __name__ == "__main__":
    main()
