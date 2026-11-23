"""Evaluate the pre-registered robustness (R1-R4) and mechanism (H-order vs H-width) hypotheses from capacity_*.json files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

GRID = ["mid50", "mid45", "mid42", "burst"]  # common grid for B2TP / B2TV / B2TD
ORDER = ["B1", "B2", "B2T", "B2TP", "B2TV"]
LEVELS = ["medium", "mid65", "mid50", "mid45", "mid42", "burst"]


def heaviest_pass(cells: dict, config: str, levels: list[str]):
    best = None
    for level in levels:
        cell = cells.get(f"{config}/{level}")
        if cell is None:
            continue
        if cell["pass"]:
            best = level
        else:
            break
    return best


def fmt(cell) -> str:
    return "  -  " if cell is None else f"{cell['chat']:.2f}/{cell['doc']:.2f}{'*' if cell['pass'] else ' '}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", required=True, help="seed=path pairs, e.g. 7=results/real/capacity_seed7.json")
    parser.add_argument("--out", default="results/real/robustness_summary.json")
    args = parser.parse_args()
    data = {pair.split("=", 1)[0]: json.loads(Path(pair.split("=", 1)[1]).read_text()) for pair in args.files}
    result: dict = {"seeds": {}}
    r2_wins = 0
    for seed, d in data.items():
        cells = d["cells"]
        print(f"=== seed {seed} (chat/doc SLO, * = pass)")
        for config in ["B1", "B2", "B2T", "B2TP", "B2TD", "B2TV"]:
            row = [fmt(cells.get(f"{config}/{l}")) for l in GRID]
            if any(cells.get(f"{config}/{l}") for l in GRID + ["mid65"]):
                print(f"  {config:5s} " + "  ".join(row))
        # common-grid comparison: heaviest level passed, requiring a pass at every lighter tested level of the grid
        hp = {c: heaviest_pass(cells, c, GRID) for c in ("B2TP", "B2TD", "B2TV")}
        order_idx = lambda x: GRID.index(x) if x else -1
        v_heavier = order_idx(hp["B2TV"]) > order_idx(hp["B2TP"])
        r2_wins += v_heavier
        # R1 ordering over all tested levels
        reach = {c: heaviest_pass(cells, c, LEVELS) for c in ORDER}
        tested = {c: any(cells.get(f"{c}/{l}") for l in LEVELS) for c in ORDER}
        idx = lambda x: LEVELS.index(x) if x else -1
        seq = [(c, reach[c]) for c in ORDER if tested[c]]
        monotone = all(idx(a[1]) <= idx(b[1]) for a, b in zip(seq, seq[1:]))
        print(f"  heaviest pass on common grid: B2TP={hp['B2TP']}, B2TD={hp['B2TD']}, B2TV={hp['B2TV']}; B2TV strictly heavier than B2TP: {v_heavier}")
        print(f"  ordering over tested levels {seq}: monotone={monotone}")
        result["seeds"][seed] = {"common_grid_heaviest_pass": hp, "b2tv_heavier_than_b2tp": v_heavier, "ordering": seq, "ordering_monotone": monotone}
    print(f"R2: B2TV passes a strictly heavier level than B2TP on {r2_wins} of {len(data)} seeds")
    result["R2_wins"] = r2_wins
    if "11" in data:
        c = data["11"]["cells"].get("B2TV/mid45")
        print("R3: seed 11 B2TV mid45", fmt(c), "->", bool(c and c["pass"]))
        result["R3"] = bool(c and c["pass"])
    if "7" in data:
        cells = data["7"]["cells"]
        print("=== mechanism (seed 7): chat/doc SLO by gateway width; V = engine priority, P = gateway chat-first (engine FCFS)")
        verdicts = []
        for load in ("mid45", "burst"):
            for width, v, p in ((24, "B2TV24", "B2TP24"), (32, "B2TV32", "B2TP32")):
                cv, cp = cells.get(f"{v}/{load}"), cells.get(f"{p}/{load}")
                if not cv or not cp:
                    continue
                dchat, ddoc = cv["chat"] - cp["chat"], cv["doc"] - cp["doc"]
                if (dchat >= 0.03 or ddoc >= 0.03) and dchat > -0.03 and ddoc > -0.03:
                    verdict = "H-order"
                elif abs(dchat) < 0.03 and abs(ddoc) < 0.03:
                    verdict = "H-width"
                else:
                    verdict = "inconclusive"
                verdicts.append(verdict)
                print(f"  {load:6s} width {width}: engine priority {fmt(cv)}  gateway chat-first {fmt(cp)}  diff chat {dchat:+.3f} doc {ddoc:+.3f} -> {verdict}")
            ref = [("width 16", "B2TP"), ("width 64 chat-first (FCFS engine)", "B2TPW"), ("width 64 engine priority", "B2TV")]
            print(f"  {load:6s} reference: " + "; ".join(f"{name} {fmt(cells.get(f'{c}/{load}'))}" for name, c in ref))
        overall = "H-order" if verdicts and all(v == "H-order" for v in verdicts) else "H-width" if verdicts and all(v == "H-width" for v in verdicts) else "mixed"
        print("mechanism verdict (pre-registered rule):", overall, verdicts)
        result["mechanism"] = {"cell_verdicts": verdicts, "overall": overall}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
