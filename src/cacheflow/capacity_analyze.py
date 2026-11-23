"""SLO-constrained capacity ladder: which load levels does each configuration pass (chat SLO >= 0.95 and doc SLO >= 0.90)?

A configuration's capacity is reported as a bracket on the tested load levels (heaviest level passed with every lighter
tested level also passed; first level above it that fails). No interpolation. Attainment is pooled over repeats and
counted over all offered requests.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from .chunk_analyze import run_detail
from .real_analyze import _gateway_index

LOADS = ["medium", "mid65", "mid50", "mid45", "mid42", "burst"]  # light to heavy
CONFIGS = ["B1", "B2", "B2T", "B2TP", "B2TD", "B2TS", "B2TV", "B2TW", "B2TPW", "B2TV24", "B2TV32", "B2TP24", "B2TP32", "B2TVD", "B2TVD4"]
LABEL = {"B1": "B1 2048 FIFO", "B2": "B2 2048 FIFO", "B2T": "B2 8192 FIFO", "B2TP": "B2 8192 chat-first (gateway)",
         "B2TD": "B2 8192 chat-first + demotion", "B2TS": "B2 8192 chat-first + slack promotion", "B2TV": "B2 8192 engine priority", "B2TW": "B2 8192 FIFO, 64 in-flight", "B2TPW": "B2 8192 chat-first, 64 in-flight", "B2TV24": "engine priority, 24 in-flight", "B2TV32": "engine priority, 32 in-flight",
         "B2TP24": "gateway chat-first, 24 in-flight", "B2TP32": "gateway chat-first, 32 in-flight",
         "B2TVD": "engine priority + gateway demotion (16 docs, did not bind)", "B2TVD4": "engine priority + gateway demotion (4 docs)"}
CHAT_TARGET, DOC_TARGET = 0.95, 0.90


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True)
    parser.add_argument("--run-prefix", required=True)
    parser.add_argument("--trace-prefix", required=True, help="manifest prefix in results/real (real60 or s11)")
    parser.add_argument("--gateway", nargs="+", required=True)
    parser.add_argument("--raw-dir", default="results/raw")
    parser.add_argument("--manifest-dir", default="results/real")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--figure", required=True)
    args = parser.parse_args()
    with open(args.registry, newline="") as file:
        run_ids = [row["run_id"] for row in csv.DictReader(file) if row["run_id"].startswith(args.run_prefix + "-")]
    keep = [rid for rid in run_ids if rid.split("-", 3)[1] in LOADS and rid.split("-", 3)[2].upper() in CONFIGS]
    gateway: dict = {}
    for path in args.gateway:
        gateway.update(_gateway_index(Path(path), set(keep)))
    groups = defaultdict(list)
    for rid in keep:
        detail = run_detail(rid, Path(args.raw_dir), gateway)
        groups[(detail["config"], detail["load"])].append(detail)
    spans = {}
    for load in LOADS:
        manifest = Path(args.manifest_dir) / f"{args.trace_prefix}_{load}.manifest.json"
        if manifest.exists():
            m = json.loads(manifest.read_text())
            spans[load] = {"offered_rps": m["requests"] / (m["span_ms"] / 1000.0), "first_visit_gap_ms": m["profile"]["first_gap"]}
    cells = {}
    for (config, load), items in groups.items():
        out = {"runs": len(items)}
        for cls, target in (("chat", CHAT_TARGET), ("doc", DOC_TARGET)):
            reqs = [p for d in items for p in d["requests_detail"] if p["cls"] == cls]
            out[cls] = sum(p["slo"] for p in reqs) / len(reqs)
        out["pass"] = out["chat"] >= CHAT_TARGET and out["doc"] >= DOC_TARGET
        out["goodput_req_per_s"] = sum(d["good"] / d["duration_s"] for d in items) / len(items)
        cells[f"{config}/{load}"] = out
    brackets = {}
    for config in CONFIGS:
        tested = [l for l in LOADS if f"{config}/{l}" in cells]
        if not tested:
            continue
        last_pass, first_fail = None, None
        for load in tested:
            if cells[f"{config}/{load}"]["pass"]:
                if first_fail is None:
                    last_pass = load
            elif first_fail is None:
                first_fail = load
        brackets[config] = {"tested": tested, "heaviest_pass": last_pass, "first_fail": first_fail,
                            "heaviest_pass_offered_rps": spans.get(last_pass, {}).get("offered_rps") if last_pass else None}
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps({"targets": {"chat": CHAT_TARGET, "doc": DOC_TARGET}, "load_levels": spans,
                                               "cells": cells, "capacity_brackets": brackets}, indent=1, sort_keys=True) + "\n")
    for config, b in brackets.items():
        rps = b["heaviest_pass_offered_rps"]
        print(f"{LABEL[config]:38s} heaviest pass: {b['heaviest_pass'] or 'below tested range':8s} "
              f"({'%.2f req/s' % rps if rps else '-'}), first fail: {b['first_fail'] or 'none up to ' + b['tested'][-1]}")
    for load in LOADS:
        row = [f"{c}:{cells[f'{c}/{load}']['chat']:.2f}/{cells[f'{c}/{load}']['doc']:.2f}{'*' if cells[f'{c}/{load}']['pass'] else ''}"
               for c in CONFIGS if f"{c}/{load}" in cells]
        print(f"{load:7s} {'%.1f req/s' % spans[load]['offered_rps'] if load in spans else '':11s} " + "  ".join(row))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    configs = [c for c in CONFIGS if c in brackets]
    fig, ax = plt.subplots(figsize=(8.2, 0.6 * len(configs) + 1.6))
    for i, config in enumerate(configs):
        for j, load in enumerate(LOADS):
            cell = cells.get(f"{config}/{load}")
            if not cell:
                ax.add_patch(plt.Rectangle((j, i), 1, 1, color="#EEEEEE"))
                continue
            ax.add_patch(plt.Rectangle((j, i), 1, 1, color="#B7E4C7" if cell["pass"] else "#F4B6B6", ec="white"))
            ax.text(j + 0.5, i + 0.5, f"{cell['chat']:.2f} / {cell['doc']:.2f}", ha="center", va="center", fontsize=8)
    ax.set_xlim(0, len(LOADS))
    ax.set_ylim(len(configs), 0)
    ax.set_xticks([j + 0.5 for j in range(len(LOADS))],
                  [f"{l}\n{spans[l]['offered_rps']:.1f} req/s" if l in spans else l for l in LOADS], fontsize=8)
    ax.set_yticks([i + 0.5 for i in range(len(configs))], [LABEL[c] for c in configs], fontsize=8)
    ax.set_title(f"chat / doc SLO attainment (green = chat >= {CHAT_TARGET} and doc >= {DOC_TARGET}; grey = not run)", fontsize=9)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout()
    Path(args.figure).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.figure, dpi=150)


if __name__ == "__main__":
    main()
