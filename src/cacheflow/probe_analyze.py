"""Analyse isolated prefill timings: does TTFT track the number of scheduler steps, beyond token count?"""

from __future__ import annotations

import argparse
import glob
import json
import math
import random
import statistics
from pathlib import Path

import numpy as np


def load(pattern: str) -> list[dict]:
    rows = []
    for path in sorted(glob.glob(pattern)):
        rows += [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    for r in rows:
        r["mnbt"] = int(r["engine_max_num_batched_tokens"])
        r["steps"] = math.ceil(r["prompt_tokens"] / r["mnbt"])
    return rows


def fit(rows: list[dict]) -> dict:
    x = np.array([[1.0, r["prompt_tokens"] / 1000.0, r["steps"]] for r in rows])
    y = np.array([r["ttft_ms"] for r in rows])
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    return {"intercept_ms": beta[0], "ms_per_1k_tokens": beta[1], "ms_per_step": beta[2]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glob", default="results/raw/probe-mnbt*.jsonl")
    parser.add_argument("--out", default="results/real/probe_analysis.json")
    parser.add_argument("--figure", default="results/figures/policy_study/prefill_probe.png")
    args = parser.parse_args()
    rows = load(args.glob)
    result: dict = {"samples": len(rows), "by_mnbt": {}}
    for mnbt in sorted({r["mnbt"] for r in rows}):
        sel = [r for r in rows if r["mnbt"] == mnbt]
        ttft = [r["ttft_ms"] for r in sel]
        per_tok = [r["ttft_ms"] / r["prompt_tokens"] * 1000 for r in sel]
        result["by_mnbt"][mnbt] = {
            "n": len(sel), "restarts": len({r["label"] for r in sel}), "ttft_median_ms": statistics.median(ttft),
            "ttft_mean_ms": statistics.fmean(ttft), "ms_per_1k_tokens_median": statistics.median(per_tok),
            "mean_steps": statistics.fmean(r["steps"] for r in sel),
            "ttft_median_by_restart": {lab: statistics.median(r["ttft_ms"] for r in sel if r["label"] == lab)
                                       for lab in sorted({r["label"] for r in sel})},
        }
    result["fit"] = fit(rows)
    # Bootstrap over documents (each document contributes all its samples), because passes of one document are not independent.
    docs = sorted({r["doc"] for r in rows})
    rng = random.Random(0)
    boots = []
    for _ in range(2000):
        pick = [rng.choice(docs) for _ in docs]
        sample = [r for d in pick for r in rows if r["doc"] == d]
        boots.append(fit(sample))
    for key in ("ms_per_step", "ms_per_1k_tokens"):
        values = sorted(b[key] for b in boots)
        result["fit"][f"{key}_ci95"] = [values[int(0.025 * len(values))], values[int(0.975 * len(values))]]
    # Paired difference per document between 2048 and 8192 (median over samples of each document)
    paired = []
    for d in docs:
        a = [r["ttft_ms"] for r in rows if r["doc"] == d and r["mnbt"] == 2048]
        b = [r["ttft_ms"] for r in rows if r["doc"] == d and r["mnbt"] == 8192]
        if a and b:
            tokens = statistics.median(r["prompt_tokens"] for r in rows if r["doc"] == d)
            sa = math.ceil(tokens / 2048)
            sb = math.ceil(tokens / 8192)
            paired.append({"doc": d, "tokens": tokens, "steps_2048": sa, "steps_8192": sb,
                           "ttft_2048_ms": statistics.median(a), "ttft_8192_ms": statistics.median(b)})
    result["paired_docs"] = paired
    diffs = [p["ttft_2048_ms"] - p["ttft_8192_ms"] for p in paired]
    result["paired_diff_2048_minus_8192_ms"] = {"mean": statistics.fmean(diffs), "min": min(diffs), "max": max(diffs)}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    colors = {2048: "#3b6ea5", 4096: "#2a9d8f", 8192: "#d1603d"}
    for mnbt in sorted({r["mnbt"] for r in rows}):
        sel = [r for r in rows if r["mnbt"] == mnbt]
        ax.scatter([r["prompt_tokens"] for r in sel], [r["ttft_ms"] for r in sel], s=14, alpha=0.65, color=colors.get(mnbt, "gray"),
                   label=f"max_num_batched_tokens {mnbt}")
    ax.set_xlabel("prompt tokens (one real QuALITY document per request)")
    ax.set_ylabel("TTFT, isolated request (ms)")
    ax.set_title("Prefill time with no queue and no prefix-cache hit", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    Path(args.figure).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.figure, dpi=160)
    print(json.dumps({k: v for k, v in result.items() if k != "paired_docs"}, indent=1, sort_keys=True, default=float))


if __name__ == "__main__":
    main()
