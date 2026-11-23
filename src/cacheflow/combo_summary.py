"""Evaluate the pre-registered hypotheses C1-C4 for engine priority + demotion (B2TVD) against its parents B2TV and B2TD."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

GRID = ["mid45", "mid42", "burst"]
CHAT_T, DOC_T = 0.95, 0.90


def heaviest_pass(cells: dict, config: str):
    best = None
    for level in GRID:
        cell = cells.get(f"{config}/{level}")
        if cell is None or not cell["pass"]:
            break
        best = level
    return best


def idx(level):
    return GRID.index(level) if level else -1


def fmt(cell) -> str:
    return "   -    " if cell is None else f"{cell['chat']:.2f}/{cell['doc']:.2f}{'*' if cell['pass'] else ' '}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", required=True, help="seed=path pairs")
    parser.add_argument("--out", default="results/real/combo_summary.json")
    parser.add_argument("--combo", default="B2TVD", help="combined configuration to evaluate (B2TVD = attempt 1, B2TVD4 = attempt 2)")
    args = parser.parse_args()
    data = {p.split("=", 1)[0]: json.loads(Path(p.split("=", 1)[1]).read_text())["cells"] for p in args.files}
    out: dict = {"seeds": {}, "C4_cells": []}
    c1_all, c2_wins = True, 0
    for seed, cells in data.items():
        print(f"=== seed {seed} (chat/doc SLO, * = pass)")
        levels = (["mid50"] if seed == "7" else []) + GRID
        for config in ("B2TP", "B2TD", "B2TV", args.combo):
            print(f"  {config:6s} " + "  ".join(f"{l}:{fmt(cells.get(f'{config}/{l}'))}" for l in levels))
        hp = {c: heaviest_pass(cells, c) for c in ("B2TV", "B2TD", args.combo)}
        best_parent = max(idx(hp["B2TV"]), idx(hp["B2TD"]))
        c1 = idx(hp[args.combo]) >= best_parent
        c2 = idx(hp[args.combo]) > best_parent
        c1_all &= c1
        c2_wins += c2
        print(f"  heaviest pass on {GRID}: {hp}; C1 (>= best parent) {c1}, C2 (> best parent) {c2}")
        out["seeds"][seed] = {"heaviest_pass": hp, "C1": c1, "C2": c2}
        for level in levels:
            v, d, vd = (cells.get(f"{c}/{level}") for c in ("B2TV", "B2TD", args.combo))
            if not (v and d and vd):
                continue
            diff_classes = (v["doc"] < DOC_T and d["chat"] < CHAT_T) or (v["chat"] < CHAT_T and d["doc"] < DOC_T)
            if diff_classes:
                ok = vd["chat"] >= max(v["chat"], d["chat"]) - 0.03 and vd["doc"] >= max(v["doc"], d["doc"]) - 0.03
                out["C4_cells"].append({"seed": seed, "level": level, "within_0.03_of_best_parent": ok,
                                        "V": [v["chat"], v["doc"]], "D": [d["chat"], d["doc"]], "VD": [vd["chat"], vd["doc"]]})
    print(f"C1 (non-inferior on every seed): {c1_all}; C2 (strictly heavier on >= 2 of {len(data)} seeds): {c2_wins} seeds -> {c2_wins >= 2}")
    out["C1"], out["C2_wins"] = c1_all, c2_wins
    if "7" in data:
        v, vd = data["7"].get("B2TV/mid50"), data["7"].get(f"{args.combo}/mid50")
        if v and vd:
            c3 = abs(vd["chat"] - v["chat"]) <= 0.03 and abs(vd["doc"] - v["doc"]) <= 0.03
            print(f"C3 (seed 7 mid50 within 0.03 of B2TV): VD {fmt(vd)} vs V {fmt(v)} -> {c3}")
            out["C3"] = c3
    c4 = out["C4_cells"]
    for c in c4:
        print(f"C4 cell seed {c['seed']} {c['level']}: V {c['V']} D {c['D']} VD {c['VD']} -> {'ok' if c['within_0.03_of_best_parent'] else 'not within 0.03'}")
    if c4:
        print(f"C4: {sum(c['within_0.03_of_best_parent'] for c in c4)} of {len(c4)} complementary cells meet the rule")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
