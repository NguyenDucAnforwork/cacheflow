"""Policy comparison on traces with real BurstGPT arrival structure (windows w1, w2): FIFO vs gateway chat-first vs demotion."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from .chunk_analyze import cell, run_detail
from .policy_analyze import attain_diff_ci
from .real_analyze import _gateway_index

POLICIES = ["B2T", "B2TP", "B2TD"]
LABEL = {"B2T": "FIFO", "B2TP": "chat-first", "B2TD": "chat-first + demotion"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="results/bg_registry.csv")
    parser.add_argument("--gateway", nargs="+", default=["results/raw/gateway_bg_runs.jsonl"])
    parser.add_argument("--raw-dir", default="results/raw")
    parser.add_argument("--manifest-dir", default="results/real")
    parser.add_argument("--out-json", default="results/real/bg_analysis.json")
    args = parser.parse_args()
    with open(args.registry, newline="") as file:
        run_ids = [row["run_id"] for row in csv.DictReader(file)]
    gateway: dict = {}
    for path in args.gateway:
        gateway.update(_gateway_index(Path(path), set(run_ids)))
    groups = defaultdict(list)
    for rid in run_ids:
        d = run_detail(rid, Path(args.raw_dir), gateway)
        groups[(d["load"], d["config"])].append(d)
    out = {"windows": {}, "cells": {}, "comparisons": []}
    for window in sorted({k[0] for k in groups}):
        manifest = json.loads((Path(args.manifest_dir) / f"bg_{window}.manifest.json").read_text())
        out["windows"][window] = {"offered_rps": manifest["offered_rps_over_span"], **manifest["arrival_stats_independent_arrivals"],
                                  "window_real_span_s": manifest["source"]["window_real_span_s"]}
        print(f"== {window}: offered {manifest['offered_rps_over_span']:.2f} req/s, gap CV {manifest['arrival_stats_independent_arrivals']['gap_cv']:.2f}, "
              f"peak {manifest['arrival_stats_independent_arrivals']['peak_arrivals_in_one_second']}/s")
        for policy in POLICIES:
            items = groups.get((window, policy))
            if not items:
                continue
            c = cell(items)
            demoted = sum(1 for d in items for p in d["requests_detail"] if False)
            out["cells"][f"{window}/{policy}"] = {"chat_slo": c["chat"]["slo_attainment"], "doc_slo": c["doc"]["slo_attainment"],
                                                  "chat_p95_ms": c["chat"]["ttft_p95_ms"], "doc_p95_ms": c["doc"]["ttft_p95_ms"],
                                                  "goodput": c["goodput_req_per_s"], "duration_s": c["duration_s"], "runs": c["n_runs"]}
            print(f"  {LABEL[policy]:24s} chat SLO {c['chat']['slo_attainment']:.2f} p95 {c['chat']['ttft_p95_ms']:.0f} ms | "
                  f"doc SLO {c['doc']['slo_attainment']:.2f} p95 {c['doc']['ttft_p95_ms']:.0f} ms | goodput {c['goodput_req_per_s']:.2f} | runs {c['n_runs']}")
        for a, b in (("B2T", "B2TP"), ("B2TP", "B2TD")):
            if (window, a) in groups and (window, b) in groups:
                for cls in ("chat", "doc"):
                    def by_id(items):
                        res = defaultdict(list)
                        for d in items:
                            for p in d["requests_detail"]:
                                if p["cls"] == cls:
                                    res[p["request_id"]].append(p["slo"])
                        return res
                    sa, sb = by_id(groups[(window, a)]), by_id(groups[(window, b)])
                    lo, hi = attain_diff_ci(sa, sb)
                    att = lambda s: sum(x for v in s.values() for x in v) / sum(len(v) for v in s.values())
                    item = {"window": window, "class": cls, "from": a, "to": b, "slo_diff": att(sb) - att(sa), "ci95": [lo, hi]}
                    out["comparisons"].append(item)
                    print(f"  {cls:4s} {LABEL[a]} -> {LABEL[b]}: SLO diff {item['slo_diff']:+.2f} CI [{lo:+.2f}, {hi:+.2f}]")
    Path(args.out_json).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
