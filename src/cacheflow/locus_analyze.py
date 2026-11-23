"""3-way decomposition of the document-outcome correlation: queue location vs documents in flight vs demotion order (docs/locus_prereg.md).

Series (decisive cells, 6 runs each): V = engine priority, no cap; S4 = engine priority with vLLM max_num_seqs 4 (queue in the engine);
F4 = engine priority, documents capped at 4 at the gateway, FIFO (queue at the gateway); VD4 = cap 4 with demotion order; D = gateway chat-first + demotion.
The statistic is the outcome design effect averaged over the 4 cells, with a 95% bootstrap interval over runs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .analyze import read_jsonl
from .real_analyze import _meets_slo
from .stats_analyze import CELLS, CHAT_T, DOC_T, PREFIX
from .variance_investigate import load_cell

SERIES = [("V engine priority, no cap", "B2TV"), ("S4 max_num_seqs 4 (queue in engine)", "B2TVS4"), ("F4 cap 4 at gateway, FIFO", "B2TVF4"),
          ("VD4 cap 4 + demotion order", "B2TVD4"), ("D chat-first + demotion", "B2TD"), ("P gateway chat-first", "B2TP")]


def ok_matrix(raw: Path, seed: str, load: str, config: str):
    runs = load_cell(raw, seed, load, config)
    if len(runs) < 3:
        return None
    ids = sorted(set.intersection(*[set(r) for r in runs]))
    ok = np.array([[bool(_meets_slo(r[i])) for i in ids] for r in runs], dtype=float)
    order = np.argsort([runs[0][i]["scheduled_arrival_ns"] for i in ids])
    return ok[:, order]


def design_effect(ok: np.ndarray):
    ro = ok - ok.mean(axis=0)
    n = ok.shape[1]
    denom = ro.var(axis=0, ddof=1).sum() / n**2
    return float(ro.mean(axis=1).var(ddof=1) / denom) if denom > 0 else None


def chat_attainment(raw: Path, seed: str, load: str, config: str) -> float:
    vals = []
    for k in range(1, 7):
        path = raw / f"{PREFIX[seed]}-{load}-{config.lower()}-r{k}.jsonl"
        if path.exists():
            recs = [r for r in read_jsonl(path) if r["cls"] == "chat"]
            vals.append(sum(_meets_slo(r) for r in recs) / len(recs))
    return float(np.mean(vals))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="results/raw")
    parser.add_argument("--out", default="results/real/locus_analysis.json")
    parser.add_argument("--figure", default="results/figures/hardening/locus.png")
    parser.add_argument("--resamples", type=int, default=1000)
    args = parser.parse_args()
    raw = Path(args.raw_dir)
    rng = np.random.default_rng(0)
    out = {}
    print(f"{'series':40s} passes  chat    doc   docSD   DE [95% CI]            runs/cell")
    for label, cfg in SERIES:
        mats = {(s, l): ok_matrix(raw, s, l, cfg) for s, l in CELLS}
        if any(m is None for m in mats.values()):
            continue
        des, sds, docs, chats, passes = [], [], [], [], 0
        for (s, l), m in mats.items():
            att = m.mean(axis=1)
            d, c = float(att.mean()), chat_attainment(raw, s, l, cfg)
            docs.append(d); chats.append(c); sds.append(float(att.std(ddof=1))); des.append(design_effect(m))
            passes += int(c >= CHAT_T and d >= DOC_T)
        boots = []
        for _ in range(args.resamples):
            vals = []
            for m in mats.values():
                idx = rng.integers(0, m.shape[0], m.shape[0])
                de = design_effect(m[idx])
                if de is not None:
                    vals.append(de)
            boots.append(np.mean(vals))
        lo, hi = np.percentile(boots, [2.5, 97.5])
        out[cfg] = {"label": label, "passes": passes, "chat": float(np.mean(chats)), "doc": float(np.mean(docs)), "doc_sd": float(np.mean(sds)),
                    "design_effect": float(np.mean([x for x in des if x is not None])), "design_effect_ci95": [float(lo), float(hi)],
                    "cell_design_effects": des, "runs_per_cell": [m.shape[0] for m in mats.values()]}
        o = out[cfg]
        print(f"{label:40s} {passes}/4     {o['chat']:.3f}  {o['doc']:.3f}  {o['doc_sd']:.3f}   {o['design_effect']:.2f} [{lo:.2f}, {hi:.2f}]   {o['runs_per_cell']}")
    de = {k: v["design_effect"] for k, v in out.items()}
    h = {}
    if {"B2TVF4", "B2TVS4", "B2TVD4", "B2TV"} <= set(de):
        h["L1"] = de["B2TVF4"] <= 1.0
        h["L2"] = de["B2TVS4"] >= 1.3
        h["L3"] = abs(de["B2TVF4"] - de["B2TVD4"]) <= 0.4
        if h["L1"] and h["L2"]:
            reading = "(a) queue location"
        elif (not h["L1"]) and (not h["L2"]):
            reading = "(b) concurrency"
        elif h["L1"] and (not h["L2"]) and (not h["L3"]):
            reading = "the demotion order"
        else:
            reading = "inconclusive"
        print(f"\nL1 (DE(F4) <= 1.0): {h['L1']} ({de['B2TVF4']:.2f}); L2 (DE(S4) >= 1.3): {h['L2']} ({de['B2TVS4']:.2f}); L3 (|DE(F4) - DE(VD4)| <= 0.4): {h['L3']} ({abs(de['B2TVF4'] - de['B2TVD4']):.2f})")
        print(f"reading by the pre-registered rule: {reading}")
        h["reading"] = reading
    Path(args.out).write_text(json.dumps({"series": out, "hypotheses": h}, indent=1, sort_keys=True) + "\n")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cfgs = [c for _, c in SERIES if c in out]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    colors = {"B2TV": "#0072B2", "B2TVS4": "#56B4E9", "B2TVF4": "#009E73", "B2TVD4": "#E69F00", "B2TD": "#D55E00", "B2TP": "#CC79A7"}
    for ax, key, title in zip(axes, ("design_effect", "doc_sd", "doc"), ("outcome design effect (variance inflation)", "doc run-to-run SD", "mean doc attainment")):
        vals = [out[c][key] for c in cfgs]
        ax.bar(range(len(cfgs)), vals, color=[colors[c] for c in cfgs])
        if key == "design_effect":
            ax.errorbar(range(len(cfgs)), vals, yerr=[[out[c]["design_effect"] - out[c]["design_effect_ci95"][0] for c in cfgs], [out[c]["design_effect_ci95"][1] - out[c]["design_effect"] for c in cfgs]],
                        fmt="none", ecolor="black", capsize=3, linewidth=1)
        ax.set_xticks(range(len(cfgs)), [out[c]["label"].split(" ")[0] for c in cfgs], fontsize=8)
        ax.set_title(title, fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    Path(args.figure).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.figure, dpi=140)


if __name__ == "__main__":
    main()
