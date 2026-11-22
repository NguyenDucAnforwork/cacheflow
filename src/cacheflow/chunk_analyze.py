"""Load x prefill-budget study: where does chat TTFT go, and does the best budget depend on load?

Decomposes each request's arrival-based TTFT into gateway admission wait + engine time (dispatch -> first token) +
remainder, adds doc service time by visit type, preemptions and max inter-token gaps (vllm:iteration_tokens_total is recorded but did not distinguish budgets, so it is not used), and pools
repeats with paired bootstrap confidence intervals over request IDs.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

from .analyze import metric_delta, percentile, read_jsonl
from .real_analyze import SLO_TPOT_MS, SLO_TTFT_MS, _gateway_index, _meets_slo, parse_run_id

LOAD_ORDER = ["moderate", "medium", "burst"]
CONFIG_ORDER = ["B1", "B1T", "B2", "B2M", "B2T", "B2TP"]
LABEL = {"B1": "B1 2048", "B1T": "B1 8192", "B2": "B2 2048", "B2M": "B2 4096", "B2T": "B2 8192", "B2TP": "B2 8192 chat-first"}
COLORS = {"B1": "#56B4E9", "B1T": "#0072B2", "B2": "#E69F00", "B2M": "#D55E00", "B2T": "#009E73", "B2TP": "#CC79A7"}


def _p95(values):
    return percentile(values, 95)


def paired_bootstrap_p95_diff(a: dict[str, list[float]], b: dict[str, list[float]], iterations: int = 2000, seed: int = 7):
    """CI for p95(b) - p95(a), resampling request IDs jointly (same requests in both configs)."""
    ids = sorted(set(a) & set(b))
    rng = random.Random(seed)
    diffs = []
    for _ in range(iterations):
        pick = [ids[rng.randrange(len(ids))] for _ in ids]
        diffs.append(_p95([v for i in pick for v in b[i]]) - _p95([v for i in pick for v in a[i]]))
    diffs.sort()
    return diffs[int(0.025 * iterations)], diffs[int(0.975 * iterations)]


def boot_ci_p95(values: list[float], iterations: int = 2000, seed: int = 7):
    rng = random.Random(seed)
    stats = sorted(_p95([values[rng.randrange(len(values))] for _ in values]) for _ in range(iterations))
    return stats[int(0.025 * iterations)], stats[int(0.975 * iterations)]


def run_detail(run_id: str, raw_dir: Path, gateway: dict) -> dict:
    records = read_jsonl(raw_dir / f"{run_id}.jsonl")
    summary = json.loads((raw_dir / f"{run_id}.summary.json").read_text())
    delta = metric_delta(raw_dir / f"{run_id}.metrics.jsonl")
    start = min(r["scheduled_arrival_ns"] for r in records)
    duration = (max(r["complete_ns"] for r in records) - start) / 1e9
    trace, config, tag = parse_run_id(run_id)
    per_request = []
    for r in records:
        g = gateway.get((run_id, r["request_id"]), {})
        wait = g.get("queue_wait_ms")
        engine = (g["first_token_ns"] - g["dispatch_ns"]) / 1e6 if g.get("first_token_ns") and g.get("dispatch_ns") else None
        ttft = r["arrival_ttft_ms"]
        per_request.append({
            "request_id": r["request_id"], "cls": r["cls"], "ttft_ms": ttft, "gateway_wait_ms": wait, "engine_ms": engine,
            "other_ms": (ttft - wait - engine) if None not in (ttft, wait, engine) else None,
            "max_itl_ms": r.get("max_itl_ms"), "tpot_ms": r.get("tpot_ms"), "ok": r["status"] == "ok",
            "slo": _meets_slo(r), "output_tokens": r["output_tokens"],
        })
    steps = delta.get("vllm:iteration_tokens_total_count", 0.0)
    tokens = delta.get("vllm:iteration_tokens_total_sum", 0.0)
    return {
        "run_id": run_id, "load": trace, "config": config, "tag": tag, "duration_s": duration,
        "good": sum(p["slo"] for p in per_request), "requests": len(per_request),
        "engine_steps": steps, "step_tokens_sum": tokens, "mean_tokens_per_step": tokens / steps if steps else None,
        "mean_step_ms": duration * 1000 / steps if steps else None,
        "preemptions": delta.get("vllm:num_preemptions_total", 0.0),
        "computed_prefill": delta.get("vllm:request_prefill_kv_computed_tokens_sum", 0.0),
        "cpu_hit": delta.get("vllm:external_prefix_cache_hits_total", 0.0),
        "gpu_hit": delta.get("vllm:prefix_cache_hits_total", 0.0),
        "engine": {k: v for k, v in summary.items() if k.startswith("engine_") or k == "max_num_batched_tokens_marker"},
        "requests_detail": per_request,
    }


def _vals(details, cls, key):
    return [p[key] for d in details for p in d["requests_detail"] if p["cls"] == cls and p[key] is not None and p["ok"]]


def cell(details: list[dict]) -> dict:
    out = {"runs": [d["run_id"] for d in details], "n_runs": len(details)}
    for cls in ("chat", "doc"):
        ttft = _vals(details, cls, "ttft_ms")
        reqs = [p for d in details for p in d["requests_detail"] if p["cls"] == cls]
        out[cls] = {
            "n": len(reqs), "ttft_p50_ms": percentile(ttft, 50), "ttft_p95_ms": _p95(ttft),
            "ttft_p95_ci95_ms": boot_ci_p95(ttft) if ttft else None,
            "slo_attainment": sum(p["slo"] for p in reqs) / len(reqs),
            "per_run_ttft_p95_ms": [_p95([p["ttft_ms"] for p in d["requests_detail"] if p["cls"] == cls and p["ttft_ms"] is not None]) for d in details],
            "gateway_wait_mean_ms": statistics.mean(_vals(details, cls, "gateway_wait_ms")),
            "gateway_wait_p95_ms": _p95(_vals(details, cls, "gateway_wait_ms")),
            "engine_mean_ms": statistics.mean(_vals(details, cls, "engine_ms")),
            "engine_p95_ms": _p95(_vals(details, cls, "engine_ms")),
            "other_mean_ms": statistics.mean(_vals(details, cls, "other_ms")),
            "tpot_p95_ms": _p95(_vals(details, cls, "tpot_ms")),
            "max_itl_p95_ms": _p95(_vals(details, cls, "max_itl_ms")), "max_itl_max_ms": max(_vals(details, cls, "max_itl_ms")),
        }
    for q in ("q0", "q1", "q2"):  # doc service time by visit type: q0 computed, q1 GPU hit, q2 late revisit (CPU restore under B2)
        vals = [p["engine_ms"] for d in details for p in d["requests_detail"] if p["cls"] == "doc" and p["request_id"].endswith(q) and p["engine_ms"] is not None]
        out[f"doc_engine_{q}_mean_ms"] = statistics.mean(vals)
    out["goodput_req_per_s"] = statistics.mean(d["good"] / d["duration_s"] for d in details)
    for key in ("duration_s", "engine_steps", "mean_tokens_per_step", "mean_step_ms", "preemptions", "computed_prefill", "cpu_hit", "gpu_hit"):
        out[key] = statistics.mean(d[key] for d in details)
    out["engine"] = details[0]["engine"]
    return out


def figures(cells: dict, out_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    loads = [l for l in LOAD_ORDER if any(k.startswith(l + "/") for k in cells)]
    configs = [c for c in CONFIG_ORDER if any(k.endswith("/" + c) for k in cells)]

    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), constrained_layout=True)
    labelled: set = set()
    for ax, cls in zip(axes, ("chat", "doc")):
        ax.set_title(f"{cls} TTFT p95 by load (dashed = SLO)", fontsize=9)
        width = 0.8 / max(1, len(configs))
        for j, config in enumerate(configs):
            for i, load in enumerate(loads):
                c = cells.get(f"{load}/{config}")
                if not c:
                    continue
                lo, hi = c[cls]["ttft_p95_ci95_ms"]
                v = c[cls]["ttft_p95_ms"]
                ax.bar(i + (j - (len(configs) - 1) / 2) * width, v / 1000, width * 0.95, color=COLORS[config],
                       yerr=[[(v - lo) / 1000], [(hi - v) / 1000]], error_kw={"elinewidth": 1}, label=LABEL[config] if f"{ax.get_title()}{config}" not in labelled else None)
                labelled.add(f"{ax.get_title()}{config}")
        ax.axhline(SLO_TTFT_MS[cls] / 1000, color="#444", linestyle="--", linewidth=1)
        ax.set_xticks(range(len(loads)), loads)
        ax.set_ylabel("TTFT p95 (s), 95% bootstrap CI")
        ax.set_title(f"{cls} TTFT p95 by load (dashed = SLO)", fontsize=9)
    axes[0].legend(fontsize=7)
    fig.savefig(out_dir / "ttft_p95_by_load.png", dpi=140)
    plt.close(fig)

    fig, axes = plt.subplots(1, len(loads), figsize=(4 * len(loads), 3.6), constrained_layout=True, squeeze=False)
    for ax, load in zip(axes[0], loads):
        present = [c for c in configs if f"{load}/{c}" in cells]
        for j, config in enumerate(present):
            c = cells[f"{load}/{config}"]
            parts = [c["chat"]["gateway_wait_mean_ms"], c["chat"]["engine_mean_ms"], max(0.0, c["chat"]["other_mean_ms"])]
            bottom = 0.0
            for part, color, name in zip(parts, ("#999999", "#0072B2", "#CCCCCC"), ("gateway wait", "engine (dispatch to 1st token)", "other")):
                ax.bar(j, part / 1000, bottom=bottom, color=color, label=name if j == 0 else None)
                bottom += part / 1000
        ax.set_xticks(range(len(present)), [LABEL[c].replace(" chat-first", "\nchat-first") for c in present], fontsize=7)
        ax.set_title(f"{load}: mean chat TTFT components (s)", fontsize=9)
    axes[0][0].legend(fontsize=7)
    fig.savefig(out_dir / "chat_ttft_decomposition.png", dpi=140)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), constrained_layout=True)
    labelled3: set = set()
    for ax, key, title in zip(axes, ("doc_engine_q0_mean_ms", "doc_engine_q2_mean_ms", "max_itl_p95_ms"),
                              ("doc first visit (q0): mean engine time (ms)", "doc late revisit (q2): mean engine time (ms)",
                               "chat: p95 of per-request max inter-token gap (ms)")):
        width = 0.8 / max(1, len(configs))
        for j, config in enumerate(configs):
            for i, load in enumerate(loads):
                c = cells.get(f"{load}/{config}")
                if c:
                    v = c["chat"]["max_itl_p95_ms"] if key == "max_itl_p95_ms" else c[key]
                    ax.bar(i + (j - (len(configs) - 1) / 2) * width, v, width * 0.95, color=COLORS[config], label=LABEL[config] if key == "max_itl_p95_ms" and config not in labelled3 else None)
                    labelled3.add(config)
        ax.set_xticks(range(len(loads)), loads)
        ax.set_title(title, fontsize=9)
    axes[2].legend(fontsize=7)
    fig.savefig(out_dir / "service_time_and_stalls.png", dpi=140)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="results/real60_registry.csv")
    parser.add_argument("--raw-dir", default="results/raw")
    parser.add_argument("--gateway", default="results/raw/gateway.jsonl")
    parser.add_argument("--out-dir", default="results/figures/chunk_study")
    parser.add_argument("--summary-json", default="results/real/chunk_analysis.json")
    args = parser.parse_args()
    with open(args.registry, newline="") as file:
        run_ids = [row["run_id"] for row in csv.DictReader(file)]
    gateway = _gateway_index(Path(args.gateway), set(run_ids))
    details = [run_detail(rid, Path(args.raw_dir), gateway) for rid in run_ids]
    groups = defaultdict(list)
    for d in details:
        groups[f"{d['load']}/{d['config']}"].append(d)
    cells = {key: cell(items) for key, items in groups.items()}
    comparisons = []
    for load in LOAD_ORDER:
        for a, b in (("B2", "B2T"), ("B2T", "B2TP"), ("B2", "B2M"), ("B1", "B1T")):
            if f"{load}/{a}" in groups and f"{load}/{b}" in groups:
                for cls in ("chat", "doc"):
                    def by_id(items):
                        out = defaultdict(list)
                        for d in items:
                            for p in d["requests_detail"]:
                                if p["cls"] == cls and p["ttft_ms"] is not None:
                                    out[p["request_id"]].append(p["ttft_ms"])
                        return out
                    ia, ib = by_id(groups[f"{load}/{a}"]), by_id(groups[f"{load}/{b}"])
                    lo, hi = paired_bootstrap_p95_diff(ia, ib)
                    pa = _p95([v for vs in ia.values() for v in vs])
                    pb = _p95([v for vs in ib.values() for v in vs])
                    comparisons.append({"load": load, "class": cls, "from": a, "to": b, "p95_from_ms": pa, "p95_to_ms": pb,
                                        "p95_diff_ms": pb - pa, "diff_ci95_ms": [lo, hi]})
    for d in details:
        d.pop("requests_detail")
    Path(args.summary_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary_json).write_text(json.dumps({"slo": {"ttft_ms": SLO_TTFT_MS, "tpot_ms": SLO_TPOT_MS}, "runs": details,
                                                   "cells": cells, "paired_p95_comparisons": comparisons}, indent=1, sort_keys=True) + "\n")
    figures(cells, Path(args.out_dir))
    for key in sorted(cells, key=lambda k: (LOAD_ORDER.index(k.split("/")[0]), CONFIG_ORDER.index(k.split("/")[1]))):
        c = cells[key]
        print(key, f"chat p95={c['chat']['ttft_p95_ms']:.0f} {tuple(round(x) for x in c['chat']['ttft_p95_ci95_ms'])} slo={c['chat']['slo_attainment']:.2f}",
              f"doc p95={c['doc']['ttft_p95_ms']:.0f} slo={c['doc']['slo_attainment']:.2f}", f"docEng q0/q2={c['doc_engine_q0_mean_ms']:.0f}/{c['doc_engine_q2_mean_ms']:.0f}",
              f"gwwait chat={c['chat']['gateway_wait_mean_ms']:.0f} eng chat={c['chat']['engine_mean_ms']:.0f} maxITLp95={c['chat']['max_itl_p95_ms']:.0f}")
    for item in comparisons:
        print(item["load"], item["class"], f"{item['from']}->{item['to']}", f"p95 {item['p95_from_ms']:.0f}->{item['p95_to_ms']:.0f}",
              f"diff {item['p95_diff_ms']:.0f} CI [{item['diff_ci95_ms'][0]:.0f}, {item['diff_ci95_ms'][1]:.0f}]")


if __name__ == "__main__":
    main()
