"""Document-cap sweep for engine priority + demotion: pass count, attainment, run-level SD and outcome design effect per cap (M1-M4)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .stats_analyze import CELLS, CHAT_T, DOC_T, PREFIX
from .variance_investigate import load_cell
from .real_analyze import _meets_slo

# cap label -> configuration; B2TV (no document cap, equivalent to cap infinity) and B2TD (gateway demotion) are references
SERIES = [("cap 4", "B2TVD4"), ("cap 8", "B2TVD8"), ("cap 12", "B2TVD12"), ("no cap (B2TV)", "B2TV"), ("B2TD (reference)", "B2TD")]


def cell_metrics(raw: Path, seed: str, load: str, config: str):
    runs = load_cell(raw, seed, load, config)
    if len(runs) < 2:
        return None
    ids = sorted(set.intersection(*[set(r) for r in runs]))
    ok = np.array([[bool(_meets_slo(r[i])) for i in ids] for r in runs], dtype=float)
    order = np.argsort([runs[0][i]["scheduled_arrival_ns"] for i in ids])
    ok = ok[:, order]
    att = ok.mean(axis=1)
    ro = ok - ok.mean(axis=0)
    n = ok.shape[1]
    denom = ro.var(axis=0, ddof=1).sum() / n**2
    de = float(ro.mean(axis=1).var(ddof=1) / denom) if denom > 0 and len(runs) > 2 else None
    # chat attainment from the same runs
    chat = []
    for k in range(1, 7):
        path = raw / f"{PREFIX[seed]}-{load}-{config.lower()}-r{k}.jsonl"
        if path.exists():
            from .analyze import read_jsonl
            recs = [r for r in read_jsonl(path) if r["cls"] == "chat"]
            chat.append(sum(_meets_slo(r) for r in recs) / len(recs))
    return {"runs": len(runs), "doc": float(att.mean()), "chat": float(np.mean(chat)), "doc_sd": float(att.std(ddof=1)), "design_effect": de,
            "pass": bool(np.mean(chat) >= CHAT_T and att.mean() >= DOC_T)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="results/raw")
    parser.add_argument("--out", default="results/real/capsweep_analysis.json")
    parser.add_argument("--figure", default="results/figures/hardening/capsweep.png")
    args = parser.parse_args()
    raw = Path(args.raw_dir)
    out = {}
    print("cell            " + "  ".join(f"{lab:>22s}" for lab, _ in SERIES))
    for seed, load in CELLS:
        row = []
        for lab, cfg in SERIES:
            m = cell_metrics(raw, seed, load, cfg)
            out[f"{seed}/{load}/{cfg}"] = m
            row.append("            -         " if m is None else f"{m['chat']:.2f}/{m['doc']:.2f}{'*' if m['pass'] else ' '} n{m['runs']} SD{m['doc_sd']:.3f}")
        print(f"seed {seed:>2} {load:6s} " + "  ".join(f"{r:>22s}" for r in row))
    summary = {}
    print("\nper series (mean over the 4 decisive cells):")
    for lab, cfg in SERIES:
        ms = [out[f"{s}/{l}/{cfg}"] for s, l in CELLS if out[f"{s}/{l}/{cfg}"]]
        if len(ms) < 4:
            continue
        des = [m["design_effect"] for m in ms if m["design_effect"] is not None]
        summary[cfg] = {"passes": sum(m["pass"] for m in ms), "chat": float(np.mean([m["chat"] for m in ms])), "doc": float(np.mean([m["doc"] for m in ms])),
                        "doc_sd": float(np.mean([m["doc_sd"] for m in ms])), "design_effect": float(np.mean(des)) if des else None, "runs_per_cell": [m["runs"] for m in ms]}
        s = summary[cfg]
        print(f"  {lab:18s} passes {s['passes']}/4  mean chat {s['chat']:.3f} doc {s['doc']:.3f}  doc run-SD {s['doc_sd']:.3f}  outcome design effect {'n/a' if s['design_effect'] is None else format(s['design_effect'], '.2f')}  runs/cell {s['runs_per_cell']}")
    de = [summary.get(c, {}).get("design_effect") for c in ("B2TVD4", "B2TVD8", "B2TVD12", "B2TV")]
    m1 = all(x is not None for x in de) and de[0] < de[1] < de[2] < de[3]
    best = max((summary[c]["passes"] for c in ("B2TVD8", "B2TVD12") if c in summary), default=0)
    m2 = best >= 3
    best_cfg = max((c for c in ("B2TVD8", "B2TVD12") if c in summary), key=lambda c: (summary[c]["passes"], -summary[c]["doc_sd"]), default=None)
    m3 = best_cfg is not None and summary[best_cfg]["doc_sd"] <= 0.02
    print(f"\nM1 (design effect increases with the cap: DE4 < DE8 < DE12 < DE(no cap)): {m1}  {[None if x is None else round(x, 2) for x in de]}")
    print(f"M2 (a cap of 8 or 12 passes >= 3 of 4 decisive cells): {m2}  (best {best} of 4)")
    print(f"M3 (doc run-SD at the best-passing cap <= 0.02): {m3}  ({best_cfg}: {None if best_cfg is None else round(summary[best_cfg]['doc_sd'], 3)})")
    Path(args.out).write_text(json.dumps({"cells": out, "series": summary, "M1": m1, "M2": m2, "M3": m3}, indent=1, sort_keys=True) + "\n")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [lab for lab, cfg in SERIES if cfg in summary]
    cfgs = [cfg for lab, cfg in SERIES if cfg in summary]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.5))
    for ax, key, title in zip(axes, ("design_effect", "doc_sd", "doc"), ("outcome design effect (variance inflation)", "doc run-to-run SD", "mean doc attainment")):
        ax.bar(range(len(cfgs)), [summary[c][key] for c in cfgs], color=["#E69F00", "#E69F00", "#E69F00", "#0072B2", "#D55E00"][:len(cfgs)])
        ax.set_xticks(range(len(cfgs)), labels, rotation=25, fontsize=7, ha="right")
        ax.set_title(title, fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    Path(args.figure).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.figure, dpi=140)


if __name__ == "__main__":
    main()
