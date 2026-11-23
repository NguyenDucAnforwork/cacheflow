"""Queue-order study: FIFO vs chat-first vs chat-first with an age cap, across load levels (B2, max_num_batched_tokens 8192).

Reports per-class TTFT p95 and SLO attainment per (load, policy) cell, paired bootstrap differences over request IDs,
the number of docs admitted by the age cap, and two figures. Reuses the per-request decomposition of chunk_analyze.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

from .analyze import percentile
from .chunk_analyze import cell, paired_bootstrap_p95_diff, run_detail
from .real_analyze import SLO_TTFT_MS, _gateway_index

LOADS = ["medium", "mid65", "mid50", "burst"]
FIRST_GAP_MS = {"medium": 900, "mid65": 650, "mid50": 500, "burst": 400}
POLICIES = ["B2T", "B2TP", "B2TA"]
LABEL = {"B2T": "FIFO", "B2TP": "chat-first", "B2TA": "chat-first + age cap"}
COLORS = {"B2T": "#E69F00", "B2TP": "#CC79A7", "B2TA": "#009E73"}


def attain_diff_ci(a: dict[str, list[bool]], b: dict[str, list[bool]], iterations: int = 2000, seed: int = 7):
    """Paired bootstrap CI for attainment(b) - attainment(a), resampling request IDs jointly."""
    ids = sorted(set(a) & set(b))
    rng = random.Random(seed)
    diffs = []
    for _ in range(iterations):
        pick = [ids[rng.randrange(len(ids))] for _ in ids]
        va = [x for i in pick for x in a[i]]
        vb = [x for i in pick for x in b[i]]
        diffs.append(sum(vb) / len(vb) - sum(va) / len(va))
    diffs.sort()
    return diffs[int(0.025 * iterations)], diffs[int(0.975 * iterations)]


def figures(cells: dict, out_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    loads = [l for l in LOADS if any(k.startswith(l + "/") for k in cells)]
    xs = [FIRST_GAP_MS[l] for l in loads]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), constrained_layout=True)
    for ax, cls, target in zip(axes, ("chat", "doc"), (0.95, 0.90)):
        for policy in POLICIES:
            pts = [(FIRST_GAP_MS[l], cells[f"{l}/{policy}"][cls]["slo_attainment"]) for l in loads if f"{l}/{policy}" in cells]
            ax.plot(*zip(*pts), marker="o", color=COLORS[policy], label=LABEL[policy])
        ax.axhline(target, color="#444", linestyle="--", linewidth=1)
        ax.set_xlabel("spacing of first document visits (ms); smaller = heavier load")
        ax.set_xlim(max(xs) + 40, min(xs) - 40)
        ax.set_ylim(0, 1.03)
        ax.set_title(f"{cls} SLO attainment (dashed = {target:.2f} target)", fontsize=9)
    axes[0].set_ylabel("share of requests meeting TTFT and TPOT SLO")
    axes[0].legend(fontsize=8, frameon=False)
    fig.savefig(out_dir / "slo_attainment_by_load.png", dpi=140)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), constrained_layout=True)
    for ax, cls in zip(axes, ("chat", "doc")):
        for policy in POLICIES:
            pts = [(FIRST_GAP_MS[l], cells[f"{l}/{policy}"][cls]["ttft_p95_ms"] / 1000) for l in loads if f"{l}/{policy}" in cells]
            ax.plot(*zip(*pts), marker="o", color=COLORS[policy], label=LABEL[policy])
        ax.axhline(SLO_TTFT_MS[cls] / 1000, color="#444", linestyle="--", linewidth=1)
        ax.set_xlabel("spacing of first document visits (ms); smaller = heavier load")
        ax.set_xlim(max(xs) + 40, min(xs) - 40)
        ax.set_yscale("log")
        ax.set_title(f"{cls} TTFT p95 (s, log; dashed = SLO)", fontsize=9)
    axes[0].legend(fontsize=8, frameon=False)
    fig.savefig(out_dir / "ttft_p95_by_load.png", dpi=140)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="results/real60_registry.csv")
    parser.add_argument("--raw-dir", default="results/raw")
    parser.add_argument("--gateway", nargs="+", default=["results/raw/gateway_r60_runs.jsonl", "results/raw/gateway_policy_runs.jsonl"])
    parser.add_argument("--out-dir", default="results/figures/policy_study")
    parser.add_argument("--summary-json", default="results/real/policy_analysis.json")
    args = parser.parse_args()
    with open(args.registry, newline="") as file:
        run_ids = [row["run_id"] for row in csv.DictReader(file)]
    keep = []
    for rid in run_ids:
        _, load, config, _tag = rid.split("-", 3)
        if load in LOADS and config.upper() in POLICIES:
            keep.append(rid)
    gateway: dict = {}
    for path in args.gateway:
        gateway.update(_gateway_index(Path(path), set(keep)))
    details = [run_detail(rid, Path(args.raw_dir), gateway) for rid in keep]
    promoted = defaultdict(int)
    for (rid, req), row in gateway.items():
        if row.get("promoted"):
            promoted[rid] += 1
    groups = defaultdict(list)
    for d in details:
        groups[f"{d['load']}/{d['config']}"].append(d)
    cells = {key: cell(items) for key, items in groups.items()}
    for key, items in groups.items():
        cells[key]["promoted_per_run"] = [promoted.get(d["run_id"], 0) for d in items]
        cells[key]["doc_gateway_wait_max_ms"] = max(p["gateway_wait_ms"] for d in items for p in d["requests_detail"]
                                                    if p["cls"] == "doc" and p["gateway_wait_ms"] is not None)
        cells[key]["chat_slo_misses_with_first_token_over_1s"] = sum(
            1 for d in items for p in d["requests_detail"] if p["cls"] == "chat" and not p["slo"])
    comparisons = []
    for load in LOADS:
        for a, b in (("B2T", "B2TP"), ("B2T", "B2TA"), ("B2TP", "B2TA")):
            if f"{load}/{a}" not in groups or f"{load}/{b}" not in groups:
                continue
            for cls in ("chat", "doc"):
                def by_id(items, field):
                    out = defaultdict(list)
                    for d in items:
                        for p in d["requests_detail"]:
                            if p["cls"] == cls and (field != "ttft_ms" or p["ttft_ms"] is not None):
                                out[p["request_id"]].append(p[field])
                    return out
                ia, ib = by_id(groups[f"{load}/{a}"], "ttft_ms"), by_id(groups[f"{load}/{b}"], "ttft_ms")
                lo, hi = paired_bootstrap_p95_diff(ia, ib)
                pa = percentile([v for vs in ia.values() for v in vs], 95)
                pb = percentile([v for vs in ib.values() for v in vs], 95)
                sa, sb = by_id(groups[f"{load}/{a}"], "slo"), by_id(groups[f"{load}/{b}"], "slo")
                alo, ahi = attain_diff_ci(sa, sb)
                att_a = sum(x for v in sa.values() for x in v) / sum(len(v) for v in sa.values())
                att_b = sum(x for v in sb.values() for x in v) / sum(len(v) for v in sb.values())
                comparisons.append({"load": load, "class": cls, "from": a, "to": b, "p95_from_ms": pa, "p95_to_ms": pb,
                                    "p95_diff_ms": pb - pa, "p95_diff_ci95_ms": [lo, hi], "slo_from": att_a, "slo_to": att_b,
                                    "slo_diff": att_b - att_a, "slo_diff_ci95": [alo, ahi]})
    for d in details:
        d.pop("requests_detail")
    Path(args.summary_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary_json).write_text(json.dumps({"runs": details, "cells": cells, "paired_comparisons": comparisons}, indent=1, sort_keys=True) + "\n")
    figures(cells, Path(args.out_dir))
    for key in sorted(cells, key=lambda k: (LOADS.index(k.split("/")[0]), POLICIES.index(k.split("/")[1]))):
        c = cells[key]
        print(f"{key:12s} runs={c['n_runs']} chat p95={c['chat']['ttft_p95_ms']:.0f} slo={c['chat']['slo_attainment']:.2f} | "
              f"doc p95={c['doc']['ttft_p95_ms']:.0f} slo={c['doc']['slo_attainment']:.2f} | goodput={c['goodput_req_per_s']:.2f} | "
              f"chat gw wait mean={c['chat']['gateway_wait_mean_ms']:.0f} doc gw wait max={c['doc_gateway_wait_max_ms']:.0f} promoted={c['promoted_per_run']} "
              f"dur={c['duration_s']:.1f}")
    for item in comparisons:
        print(f"{item['load']:7s} {item['class']:4s} {item['from']}->{item['to']}: p95 {item['p95_from_ms']:.0f}->{item['p95_to_ms']:.0f} "
              f"({item['p95_diff_ci95_ms'][0]:.0f},{item['p95_diff_ci95_ms'][1]:.0f}); slo {item['slo_from']:.2f}->{item['slo_to']:.2f} "
              f"diff {item['slo_diff']:+.2f} CI [{item['slo_diff_ci95'][0]:+.2f},{item['slo_diff_ci95'][1]:+.2f}]")


if __name__ == "__main__":
    main()
