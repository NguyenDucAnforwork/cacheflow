"""Run-level capacity ladder: per (seed, configuration, level) mean attainment over runs, run-level bootstrap pass probability,
and the heaviest-pass bracket per configuration; evaluates the pre-registered L1-L3 (docs/ladder_capsweep_prereg.md)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .stats_analyze import CHAT_T, DOC_T, PREFIX, boot_means, run_attainment

LEVELS = ["medium", "mid65", "mid50", "mid45", "mid42", "burst"]
RATE = {"medium": 4.03, "mid65": 5.50, "mid50": 6.87, "mid45": 7.57, "mid42": 8.18, "burst": 8.64}
CONFIGS = ["B1", "B2", "B2T", "B2TP", "B2TD", "B2TV"]


def cell_runs(raw: Path, seed: str, level: str, config: str):
    out = []
    for k in range(1, 7):
        path = raw / f"{PREFIX[seed]}-{level}-{config.lower()}-r{k}.jsonl"
        if path.exists():
            out.append(run_attainment(raw, f"{PREFIX[seed]}-{level}-{config.lower()}-r{k}"))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="results/raw")
    parser.add_argument("--out", default="results/real/ladder_hardened.json")
    parser.add_argument("--figure", default="results/figures/capacity/ladder_runlevel.png")
    parser.add_argument("--resamples", type=int, default=5000)
    args = parser.parse_args()
    raw = Path(args.raw_dir)
    rng = np.random.default_rng(0)
    result = {}
    for seed in ("7", "11", "23"):
        cells = {}
        for config in CONFIGS:
            for level in LEVELS:
                runs = cell_runs(raw, seed, level, config)
                if not runs:
                    continue
                chat = np.array([r["chat"] for r in runs])
                doc = np.array([r["doc"] for r in runs])
                if len(runs) >= 3:
                    bc, bd = boot_means(chat, rng, args.resamples), boot_means(doc, rng, args.resamples)
                    p_pass = float(np.mean((bc >= CHAT_T) & (bd >= DOC_T)))
                else:
                    p_pass = None
                cells[f"{config}/{level}"] = {"runs": len(runs), "chat": float(chat.mean()), "doc": float(doc.mean()),
                                             "pass": bool(chat.mean() >= CHAT_T and doc.mean() >= DOC_T), "p_pass": p_pass}
        brackets = {}
        for config in CONFIGS:
            best, first_fail = None, None
            for level in LEVELS:
                c = cells.get(f"{config}/{level}")
                if c is None:
                    continue
                if c["pass"] and first_fail is None:
                    best = level
                elif not c["pass"] and first_fail is None:
                    first_fail = level
            if any(f"{config}/{l}" in cells for l in LEVELS):
                brackets[config] = {"heaviest_pass": best, "first_fail": first_fail, "offered_rps": RATE.get(best) if best else None}
        result[seed] = {"cells": cells, "brackets": brackets}
        print(f"=== seed {seed}")
        for config in CONFIGS:
            b = brackets.get(config)
            if not b:
                continue
            row = "  ".join(f"{l}:{cells[f'{config}/{l}']['chat']:.2f}/{cells[f'{config}/{l}']['doc']:.2f}{'*' if cells[f'{config}/{l}']['pass'] else ' '}(n{cells[f'{config}/{l}']['runs']})"
                            for l in LEVELS if f"{config}/{l}" in cells)
            print(f"  {config:5s} heaviest pass {str(b['heaviest_pass']):7s} first fail {str(b['first_fail']):7s} | {row}")
    # pre-registered hypotheses
    c7, c23, c11 = result["7"]["cells"], result["23"]["cells"], result["11"]["cells"]
    L1 = (not c7["B1/mid65"]["pass"]) and c7["B2/mid65"]["pass"]
    L2 = all(c7[f"{c}/mid50"]["pass"] for c in ("B2TP", "B2TD", "B2TV"))
    L3 = c23["B2TP/mid50"]["pass"] and (not c23["B2TD/mid42"]["pass"]) and c11["B2T/mid50"]["pass"]
    print(f"\nL1 (seed 7: B1 fails mid65, B2 passes mid65): {L1}  B1 {c7['B1/mid65']['chat']:.3f}/{c7['B1/mid65']['doc']:.3f} (n{c7['B1/mid65']['runs']}), B2 {c7['B2/mid65']['chat']:.3f}/{c7['B2/mid65']['doc']:.3f} (n{c7['B2/mid65']['runs']})")
    print(f"L2 (seed 7: B2TP, B2TD, B2TV all pass mid50): {L2}  " + ", ".join(f"{c} {c7[f'{c}/mid50']['chat']:.3f}/{c7[f'{c}/mid50']['doc']:.3f} (n{c7[f'{c}/mid50']['runs']})" for c in ("B2TP", "B2TD", "B2TV")))
    print(f"L3 (seed 23 B2TP passes mid50, B2TD fails mid42; seed 11 B2T passes mid50): {L3}  "
          f"{c23['B2TP/mid50']['chat']:.3f}/{c23['B2TP/mid50']['doc']:.3f}, {c23['B2TD/mid42']['chat']:.3f}/{c23['B2TD/mid42']['doc']:.3f}, {c11['B2T/mid50']['chat']:.3f}/{c11['B2T/mid50']['doc']:.3f}")
    result["hypotheses"] = {"L1": L1, "L2": L2, "L3": L3}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 3.6), sharey=True)
    for ax, seed in zip(axes, ("7", "11", "23")):
        cells = result[seed]["cells"]
        for i, config in enumerate(CONFIGS):
            for j, level in enumerate(LEVELS):
                c = cells.get(f"{config}/{level}")
                if not c:
                    ax.add_patch(plt.Rectangle((j, i), 1, 1, color="#EEEEEE"))
                    continue
                ax.add_patch(plt.Rectangle((j, i), 1, 1, color="#B7E4C7" if c["pass"] else "#F4B6B6", ec="white"))
                ax.text(j + 0.5, i + 0.42, f"{c['chat']:.2f}/{c['doc']:.2f}", ha="center", va="center", fontsize=6.5)
                ax.text(j + 0.5, i + 0.75, f"n={c['runs']}", ha="center", va="center", fontsize=6, color="#444")
        ax.set_xlim(0, len(LEVELS))
        ax.set_ylim(len(CONFIGS), 0)
        ax.set_xticks([j + 0.5 for j in range(len(LEVELS))], [f"{l}\n{RATE[l]:.1f}" for l in LEVELS], fontsize=7)
        ax.set_yticks([i + 0.5 for i in range(len(CONFIGS))], CONFIGS, fontsize=8)
        ax.set_title(f"seed {seed}: chat/doc attainment, run means (green = pass)", fontsize=8)
        for side in ("top", "right", "left", "bottom"):
            ax.spines[side].set_visible(False)
        ax.tick_params(length=0)
    fig.tight_layout()
    Path(args.figure).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.figure, dpi=140)


if __name__ == "__main__":
    main()
