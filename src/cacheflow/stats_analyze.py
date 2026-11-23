"""Run-level statistics for the decisive cells: per-run SLO attainment, run-level bootstrap intervals, pass probability, H1-H4."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .analyze import read_jsonl
from .real_analyze import _meets_slo

CELLS = [("7", "mid45"), ("23", "mid45"), ("11", "mid42"), ("11", "burst")]
CONFIGS = ["B2TP", "B2TD", "B2TV"]
PREFIX = {"7": "r60", "11": "s11", "23": "s23"}
CHAT_T, DOC_T = 0.95, 0.90
LABEL = {"B2TP": "gateway chat-first", "B2TD": "chat-first + demotion", "B2TV": "engine priority"}


def run_attainment(raw: Path, run_id: str):
    records = read_jsonl(raw / f"{run_id}.jsonl")
    out = {}
    for cls in ("chat", "doc"):
        reqs = [r for r in records if r["cls"] == cls]
        out[cls] = sum(_meets_slo(r) for r in reqs) / len(reqs)
    return out


def collect(raw: Path, max_repeat: int = 6):
    data = {}
    for seed, load in CELLS:
        for config in CONFIGS:
            runs = {}
            for k in range(1, max_repeat + 1):
                rid = f"{PREFIX[seed]}-{load}-{config.lower()}-r{k}"
                if (raw / f"{rid}.jsonl").exists():
                    runs[k] = run_attainment(raw, rid)
            data[(seed, load, config)] = runs
    return data


def boot_means(values: np.ndarray, rng: np.random.Generator, n: int) -> np.ndarray:
    idx = rng.integers(0, len(values), size=(n, len(values)))
    return values[idx].mean(axis=1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="results/raw")
    parser.add_argument("--out", default="results/real/hardening_analysis.json")
    parser.add_argument("--figure", default="results/figures/hardening/decisive_cells.png")
    parser.add_argument("--resamples", type=int, default=10000)
    args = parser.parse_args()
    rng = np.random.default_rng(0)
    data = collect(Path(args.raw_dir))
    cells = {}
    for key, runs in data.items():
        if not runs:
            continue
        chat = np.array([v["chat"] for v in runs.values()])
        doc = np.array([v["doc"] for v in runs.values()])
        bc, bd = boot_means(chat, rng, args.resamples), boot_means(doc, rng, args.resamples)
        old = [v for k, v in runs.items() if k <= 2]
        new = [v for k, v in runs.items() if k >= 3]
        cells["/".join(key)] = {
            "n_runs": len(runs), "chat_runs": chat.tolist(), "doc_runs": doc.tolist(),
            "chat_mean": float(chat.mean()), "doc_mean": float(doc.mean()),
            "chat_sd": float(chat.std(ddof=1)) if len(chat) > 1 else None, "doc_sd": float(doc.std(ddof=1)) if len(doc) > 1 else None,
            "chat_ci95": [float(np.percentile(bc, 2.5)), float(np.percentile(bc, 97.5))],
            "doc_ci95": [float(np.percentile(bd, 2.5)), float(np.percentile(bd, 97.5))],
            "pass": bool(chat.mean() >= CHAT_T and doc.mean() >= DOC_T),
            "pass_probability": float(np.mean((bc >= CHAT_T) & (bd >= DOC_T))),
            "mean_r1_r2": [float(np.mean([v["chat"] for v in old])), float(np.mean([v["doc"] for v in old]))] if old else None,
            "mean_r3_plus": [float(np.mean([v["chat"] for v in new])), float(np.mean([v["doc"] for v in new]))] if new else None,
        }
    print("cell                       runs  chat mean [95% CI]        doc mean [95% CI]         SD chat/doc   pass  P(pass)")
    for (seed, load) in CELLS:
        for config in CONFIGS:
            c = cells.get(f"{seed}/{load}/{config}")
            if not c:
                continue
            print(f"seed {seed:>2} {load:6s} {config:5s} {c['n_runs']:3d}   {c['chat_mean']:.3f} [{c['chat_ci95'][0]:.3f},{c['chat_ci95'][1]:.3f}]   "
                  f"{c['doc_mean']:.3f} [{c['doc_ci95'][0]:.3f},{c['doc_ci95'][1]:.3f}]   {c['chat_sd'] or 0:.3f}/{c['doc_sd'] or 0:.3f}   "
                  f"{'PASS' if c['pass'] else 'fail'}  {c['pass_probability']:.2f}")
    # hypotheses
    passes = {cfg: sum(cells.get(f"{s}/{l}/{cfg}", {}).get("pass", False) for s, l in CELLS) for cfg in CONFIGS}
    h1 = passes["B2TV"] >= 2 and passes["B2TV"] > passes["B2TP"]
    h2 = passes["B2TD"] >= passes["B2TV"]
    sds = [c["doc_sd"] for c in cells.values() if c["doc_sd"] is not None]
    h3_count = sum(sd >= 0.03 for sd in sds)
    h3 = h3_count >= 6 and len(sds) >= 12
    print(f"\npasses over the 4 decisive cells: {passes}")
    print(f"H1 (B2TV passes >= 2 cells and more than B2TP): {h1}")
    print(f"H2 (B2TD passes >= as many cells as B2TV): {h2}")
    print(f"H3 (doc run-to-run SD >= 0.03 in >= 6 of 12 cells): {h3_count} of {len(sds)} cells -> {h3}")
    h4 = {}
    for a, b in (("B2TP", "B2TV"), ("B2TV", "B2TD")):
        count, detail = 0, []
        for s, l in CELLS:
            ca, cb = cells.get(f"{s}/{l}/{a}"), cells.get(f"{s}/{l}/{b}")
            if not ca or not cb:
                continue
            excl = []
            for cls in ("chat", "doc"):
                xa, xb = np.array(ca[f"{cls}_runs"]), np.array(cb[f"{cls}_runs"])
                diff = boot_means(xb, rng, args.resamples) - boot_means(xa, rng, args.resamples)
                lo, hi = np.percentile(diff, [2.5, 97.5])
                excl.append({"class": cls, "diff": float(xb.mean() - xa.mean()), "ci95": [float(lo), float(hi)], "excludes_zero": bool(lo > 0 or hi < 0)})
            detail.append({"cell": f"seed {s} {l}", "classes": excl})
            count += any(e["excludes_zero"] for e in excl)
        h4[f"{a}->{b}"] = {"cells_excluding_zero": count, "detail": detail}
        print(f"H4 {LABEL[a]} -> {LABEL[b]}: interval excludes 0 on at least one class in {count} of {len(detail)} cells")
        for d in detail:
            print("    " + d["cell"] + ": " + ", ".join(f"{e['class']} {e['diff']:+.3f} [{e['ci95'][0]:+.3f},{e['ci95'][1]:+.3f}]{'*' if e['excludes_zero'] else ''}" for e in d["classes"]))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"cells": cells, "passes": passes, "H1": h1, "H2": h2, "H3": {"cells_ge_0.03": h3_count, "of": len(sds), "met": h3}, "H4": h4},
                                         indent=1, sort_keys=True) + "\n")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, len(CELLS), figsize=(3.1 * len(CELLS), 5.6), sharey="row")
    colors = {"B2TP": "#CC79A7", "B2TD": "#D55E00", "B2TV": "#0072B2"}
    for j, (s, l) in enumerate(CELLS):
        for i, cls in enumerate(("chat", "doc")):
            ax = axes[i][j]
            for x, cfg in enumerate(CONFIGS):
                c = cells.get(f"{s}/{l}/{cfg}")
                if not c:
                    continue
                ys = c[f"{cls}_runs"]
                ax.scatter([x] * len(ys) + np.random.default_rng(1).uniform(-0.12, 0.12, len(ys)), ys, s=14, color=colors[cfg], alpha=0.7)
                ax.hlines(c[f"{cls}_mean"], x - 0.28, x + 0.28, color="black", linewidth=2)
                ax.vlines(x, *c[f"{cls}_ci95"], color="black", linewidth=1)
            ax.axhline(CHAT_T if cls == "chat" else DOC_T, color="#444", linestyle="--", linewidth=1)
            ax.set_xticks(range(len(CONFIGS)), ["chat-first", "+demotion", "engine prio"] if i == 1 else [""] * len(CONFIGS), fontsize=7)
            if j == 0:
                ax.set_ylabel(f"{cls} SLO attainment per run")
            if i == 0:
                ax.set_title(f"seed {s}, {l}", fontsize=9)
    fig.suptitle("Per-run SLO attainment (dots), mean (bar) and 95% run-level bootstrap interval (line); dashed = target", fontsize=9)
    fig.tight_layout()
    Path(args.figure).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.figure, dpi=140)


if __name__ == "__main__":
    main()
