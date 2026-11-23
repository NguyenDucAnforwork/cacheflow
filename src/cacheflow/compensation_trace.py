"""Direct trace of the 'compensating flips' mechanism for gateway demotion (B2TD) using the gateway's `demoted` flag per request.

For each run of B2TD in the 4 decisive cells: misses among documents the gateway demoted (M_dem), misses among the others (M_sav) and the total (M_tot).
If demotion absorbs load shifts, M_dem and M_sav move in opposite directions across runs (negative within-cell covariance) and Var(M_tot) is much smaller
than Var(M_dem) + Var(M_sav). Compared with the total-misses variance of engine priority (no demotion) in the same cells.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import numpy as np

from .analyze import read_jsonl
from .real_analyze import _meets_slo
from .stats_analyze import CELLS, PREFIX


def gateway_flags(pattern: str, run_prefixes):
    flags = {}
    for path in glob.glob(pattern):
        with open(path, encoding="utf-8") as file:
            for line in file:
                if '"demoted"' not in line:
                    continue
                row = json.loads(line)
                if row["run_id"].startswith(run_prefixes):
                    flags[(row["run_id"], row["request_id"])] = bool(row.get("demoted"))
    return flags


def doc_misses(raw: Path, run_id: str):
    return {r["request_id"]: (not _meets_slo(r)) for r in read_jsonl(raw / f"{run_id}.jsonl") if r["cls"] == "doc"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="results/raw")
    parser.add_argument("--gateway-glob", default="results/raw/gateway_*_runs.jsonl")
    parser.add_argument("--out", default="results/real/compensation_trace.json")
    args = parser.parse_args()
    raw = Path(args.raw_dir)
    flags = gateway_flags(args.gateway_glob, ("r60-", "s11-", "s23-"))
    rows, centered = [], {"dem": [], "sav": [], "tot": []}
    print("cell              runs  M_tot mean/SD   M_dem mean/SD   M_sav mean/SD   corr(M_dem, M_sav)   SD(M_tot) engine priority")
    for seed, load in CELLS:
        mat = {"dem": [], "sav": [], "tot": []}
        for k in range(1, 7):
            rid = f"{PREFIX[seed]}-{load}-b2td-r{k}"
            if not (raw / f"{rid}.jsonl").exists():
                continue
            miss = doc_misses(raw, rid)
            dem = sum(miss[r] for r in miss if flags.get((rid, r), False))
            sav = sum(miss[r] for r in miss if not flags.get((rid, r), False))
            mat["dem"].append(dem), mat["sav"].append(sav), mat["tot"].append(dem + sav)
        d, s, t = (np.array(mat[x], dtype=float) for x in ("dem", "sav", "tot"))
        v_tot = []
        for k in range(1, 7):
            rid = f"{PREFIX[seed]}-{load}-b2tv-r{k}"
            if (raw / f"{rid}.jsonl").exists():
                v_tot.append(sum(doc_misses(raw, rid).values()))
        corr = float(np.corrcoef(d, s)[0, 1]) if d.std() > 0 and s.std() > 0 else None
        rows.append({"seed": seed, "load": load, "runs": len(t), "tot_mean": float(t.mean()), "tot_sd": float(t.std(ddof=1)), "dem_mean": float(d.mean()), "dem_sd": float(d.std(ddof=1)),
                     "sav_mean": float(s.mean()), "sav_sd": float(s.std(ddof=1)), "corr_dem_sav": corr, "engine_priority_tot_sd": float(np.std(v_tot, ddof=1))})
        print(f"seed {seed:>2} {load:6s}  {len(t):3d}   {t.mean():5.1f}/{t.std(ddof=1):4.2f}     {d.mean():5.1f}/{d.std(ddof=1):4.2f}     {s.mean():5.1f}/{s.std(ddof=1):4.2f}      "
              f"{('%+.2f' % corr) if corr is not None else 'n/a':>8s}              {np.std(v_tot, ddof=1):4.2f}")
        for key, arr in (("dem", d), ("sav", s), ("tot", t)):
            centered[key] += (arr - arr.mean()).tolist()
    d, s, t = (np.array(centered[x]) for x in ("dem", "sav", "tot"))
    pooled_corr = float(np.corrcoef(d, s)[0, 1])
    var_d, var_s, var_t = d.var(ddof=1), s.var(ddof=1), t.var(ddof=1)
    cov = float(np.cov(d, s, ddof=1)[0, 1])
    print(f"\npooled within-cell (centered) over {len(t)} runs: Var(M_dem) {var_d:.2f}, Var(M_sav) {var_s:.2f}, 2*Cov {2 * cov:+.2f}, Var(M_tot) {var_t:.2f} "
          f"(= sum {var_d + var_s + 2 * cov:.2f}); corr(M_dem, M_sav) {pooled_corr:+.2f}")
    print(f"variance of total misses relative to the no-covariance sum: {var_t / (var_d + var_s):.2f}")
    Path(args.out).write_text(json.dumps({"cells": rows, "pooled": {"var_dem": float(var_d), "var_sav": float(var_s), "cov": cov, "var_tot": float(var_t), "corr": pooled_corr,
                                                                    "ratio_total_to_independent_sum": float(var_t / (var_d + var_s)), "runs": int(len(t))}}, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
