"""Chat vs doc SLO attainment plane for the decisive cells (6 runs each): where each configuration sits relative to the targets."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

CELLS = [("7", "mid45"), ("23", "mid45"), ("11", "mid42"), ("11", "burst")]
SERIES = [("gateway chat-first", "B2TP", "#CC79A7"), ("chat-first + demotion", "B2TD", "#D55E00"), ("engine priority (no cap)", "B2TV", "#0072B2"),
          ("engine priority + demotion, cap 12", "B2TVD12", "#56B4E9"), ("... cap 8", "B2TVD8", "#009E73"), ("... cap 4", "B2TVD4", "#E69F00")]


def main() -> None:
    cap = json.loads(Path("results/real/capsweep_analysis.json").read_text())["cells"]
    hard = json.loads(Path("results/real/hardening_analysis.json").read_text())["cells"]
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.4, 5))
    ax.axvspan(0.90, 1.0, ymin=0, ymax=1, color="#E8F5E9", zorder=0)
    ax.axhspan(0.95, 1.01, color="#E8F5E9", zorder=0)
    ax.axvline(0.90, color="#444", linestyle="--", linewidth=1)
    ax.axhline(0.95, color="#444", linestyle="--", linewidth=1)
    means = {}
    for label, cfg, color in SERIES:
        pts = []
        for seed, load in CELLS:
            c = hard.get(f"{seed}/{load}/{cfg}")
            if c:
                pts.append((c["doc_mean"], c["chat_mean"]))
            else:
                m = cap.get(f"{seed}/{load}/{cfg}")
                if m:
                    pts.append((m["doc"], m["chat"]))
        if not pts:
            continue
        xs, ys = zip(*pts)
        ax.scatter(xs, ys, s=18, color=color, alpha=0.45)
        ax.scatter([np.mean(xs)], [np.mean(ys)], s=95, color=color, edgecolor="black", linewidth=0.8, label=label, zorder=3)
        means[cfg] = (float(np.mean(xs)), float(np.mean(ys)))
    ax.set_xlabel("doc SLO attainment (mean of 6 runs per cell)")
    ax.set_ylabel("chat SLO attainment")
    ax.set_xlim(0.80, 1.0)
    ax.set_ylim(0.88, 1.01)
    ax.set_title("Four decisive cells: small dots = cells, large dots = mean over cells\n(green = both targets met)", fontsize=9)
    ax.legend(fontsize=7, frameon=False, loc="lower left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    Path("results/figures/hardening").mkdir(parents=True, exist_ok=True)
    fig.savefig("results/figures/hardening/chat_doc_plane.png", dpi=150)
    for cfg, (x, y) in means.items():
        print(f"{cfg:8s} mean doc {x:.3f} chat {y:.3f}")


if __name__ == "__main__":
    main()
