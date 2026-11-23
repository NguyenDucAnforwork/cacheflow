"""Why do some configurations have a larger run-to-run spread in doc SLO attainment?

Uses the 12 decisive cells (6 runs each). For each (cell, config) it builds the request x run matrix of TTFT and SLO outcomes and computes:
  * observed run-to-run SD of doc attainment;
  * the SD predicted if every request flipped independently with its own empirical pass rate p_i (sqrt(sum p_i (1-p_i)) / n);
  * the number of *unstable* requests (pass rate strictly between 0 and 1), by visit type (q0 first visit, q1 GPU hit, q2 late revisit);
  * how much of the doc TTFT mass sits in a band around the 3 s SLO, and the cross-run SD of each request's TTFT.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .analyze import read_jsonl
from .real_analyze import _meets_slo
from .stats_analyze import CELLS, CONFIGS, PREFIX

BAND_MS = 500.0
SLO_MS = 3000.0


def load_cell(raw: Path, seed: str, load: str, config: str):
    runs = []
    for k in range(1, 7):
        rid = f"{PREFIX[seed]}-{load}-{config.lower()}-r{k}"
        path = raw / f"{rid}.jsonl"
        if path.exists():
            runs.append({r["request_id"]: r for r in read_jsonl(path) if r["cls"] == "doc"})
    return runs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="results/raw")
    parser.add_argument("--out", default="results/real/variance_investigation.json")
    parser.add_argument("--figure", default="results/figures/hardening/variance_mechanism.png")
    args = parser.parse_args()
    raw = Path(args.raw_dir)
    rows = []
    for seed, load in CELLS:
        for config in CONFIGS:
            runs = load_cell(raw, seed, load, config)
            if len(runs) < 4:
                continue
            ids = sorted(set.intersection(*[set(r) for r in runs]))
            ttft = np.array([[r[i]["arrival_ttft_ms"] if r[i]["arrival_ttft_ms"] is not None else np.nan for i in ids] for r in runs])  # runs x requests
            ok = np.array([[bool(_meets_slo(r[i])) for i in ids] for r in runs], dtype=float)
            att = ok.mean(axis=1)
            p = ok.mean(axis=0)
            pred_sd = float(np.sqrt((p * (1 - p)).sum()) / len(ids))
            obs_sd = float(att.std(ddof=1))
            unstable = (p > 0) & (p < 1)
            by_visit = {q: int(unstable[[i.endswith(q) for i in ids]].sum()) for q in ("q0", "q1", "q2")}
            mean_ttft = np.nanmean(ttft, axis=0)
            band = np.abs(mean_ttft - SLO_MS) <= BAND_MS
            req_sd = np.nanstd(ttft, axis=0, ddof=1)
            # common-mode (design effect): variance of the per-run mean residual relative to what independent requests would give
            order = np.argsort([runs[0][i]["scheduled_arrival_ns"] for i in ids])
            col = np.where(np.isnan(ttft), np.nanmean(ttft, axis=0), ttft)[:, order]
            resid = col - col.mean(axis=0)
            n_docs = resid.shape[1]
            de_ttft = float(resid.mean(axis=1).var(ddof=1) / (resid.var(axis=0, ddof=1).sum() / n_docs**2))
            okc = ok[:, order]
            ro = okc - okc.mean(axis=0)
            denom_ok = ro.var(axis=0, ddof=1).sum() / n_docs**2
            de_ok = float(ro.mean(axis=1).var(ddof=1) / denom_ok) if denom_ok > 0 else None
            lag1 = float(np.corrcoef(resid[:, :-1].ravel(), resid[:, 1:].ravel())[0, 1])
            rows.append({
                "seed": seed, "load": load, "config": config, "runs": len(runs), "docs": len(ids),
                "obs_sd": obs_sd, "pred_sd_independent": pred_sd, "unstable_requests": int(unstable.sum()), "unstable_by_visit": by_visit,
                "share_in_band": float(band.mean()), "share_far_miss": float((mean_ttft > SLO_MS + BAND_MS).mean()), "share_far_hit": float((mean_ttft < SLO_MS - BAND_MS).mean()),
                "median_request_ttft_sd_ms": float(np.median(req_sd)), "mean_request_ttft_sd_in_band_ms": float(np.mean(req_sd[band])) if band.any() else None,
                "mean_doc_attainment": float(att.mean()), "design_effect_ttft": de_ttft, "design_effect_outcome": de_ok, "lag1_residual_autocorr": lag1,
            })
    by_cfg = defaultdict(list)
    for r in rows:
        by_cfg[r["config"]].append(r)
    print(f"{'cell':20s} {'cfg':5s} obsSD predSD(indep) unstable(q0/q1/q2) in-band far-miss far-hit medReqSD(ms)")
    for r in rows:
        u = r["unstable_by_visit"]
        print(f"seed {r['seed']:>2} {r['load']:6s}   {r['config']:5s} {r['obs_sd']:.3f}  {r['pred_sd_independent']:.3f}        {r['unstable_requests']:2d} ({u['q0']}/{u['q1']}/{u['q2']})      "
              f"{r['share_in_band']:.2f}    {r['share_far_miss']:.2f}     {r['share_far_hit']:.2f}    {r['median_request_ttft_sd_ms']:.0f}   DE(ttft) {r['design_effect_ttft']:.1f} DE(out) {r['design_effect_outcome'] if r['design_effect_outcome'] is None else round(r['design_effect_outcome'],1)} lag1 {r['lag1_residual_autocorr']:+.2f}")
    print("\nper configuration (mean over the 4 decisive cells):")
    summary = {}
    for cfg, items in by_cfg.items():
        m = lambda key: float(np.mean([i[key] for i in items]))
        summary[cfg] = {k: m(k) for k in ("obs_sd", "pred_sd_independent", "unstable_requests", "share_in_band", "share_far_miss", "share_far_hit", "median_request_ttft_sd_ms", "design_effect_ttft", "lag1_residual_autocorr")}
        summary[cfg]["design_effect_outcome"] = float(np.mean([i["design_effect_outcome"] for i in items if i["design_effect_outcome"] is not None]))
        s = summary[cfg]
        print(f"  {cfg:5s} obs SD {s['obs_sd']:.3f}  independent-flip SD {s['pred_sd_independent']:.3f}  unstable {s['unstable_requests']:.1f}  in-band {s['share_in_band']:.2f}  "
              f"far-miss {s['share_far_miss']:.2f}  far-hit {s['share_far_hit']:.2f}  median per-request TTFT SD {s['median_request_ttft_sd_ms']:.0f} ms | "
              f"design effect: TTFT {s['design_effect_ttft']:.2f}, outcome {s['design_effect_outcome']:.2f}; lag-1 residual autocorr {s['lag1_residual_autocorr']:+.2f}")
    obs = np.array([r["obs_sd"] for r in rows])
    pred = np.array([r["pred_sd_independent"] for r in rows])
    unst = np.array([r["unstable_requests"] for r in rows], dtype=float)
    band = np.array([r["share_in_band"] for r in rows])
    corr = lambda a, b: float(np.corrcoef(a, b)[0, 1])
    stats = {"corr_obs_pred": corr(obs, pred), "corr_obs_unstable": corr(obs, unst), "corr_obs_in_band": corr(obs, band)}
    print(f"\ncorrelation over the 12 (cell, config) points: observed SD vs independent-flip SD {stats['corr_obs_pred']:.2f}, vs unstable count {stats['corr_obs_unstable']:.2f}, vs in-band share {stats['corr_obs_in_band']:.2f}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"rows": rows, "by_config": summary, "correlations": stats}, indent=1, sort_keys=True) + "\n")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"B2TP": "#CC79A7", "B2TD": "#D55E00", "B2TV": "#0072B2"}
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.8))
    for cfg in CONFIGS:
        items = by_cfg[cfg]
        axes[0].scatter([i["pred_sd_independent"] for i in items], [i["obs_sd"] for i in items], color=colors[cfg], label=cfg)
        axes[1].scatter([i["share_in_band"] for i in items], [i["obs_sd"] for i in items], color=colors[cfg])
        axes[2].bar(cfg, np.mean([i["unstable_requests"] for i in items]), color=colors[cfg])
    lim = max(obs.max(), pred.max()) * 1.05
    axes[0].plot([0, lim], [0, lim], color="#777", linewidth=1, linestyle="--")
    axes[0].set_xlabel("SD predicted from independent per-request flips")
    axes[0].set_ylabel("observed run-to-run SD of doc attainment")
    axes[0].legend(fontsize=8, frameon=False)
    axes[1].set_xlabel("share of doc requests with mean TTFT within 0.5 s of the 3 s SLO")
    axes[1].set_ylabel("observed run-to-run SD")
    axes[2].set_ylabel("unstable doc requests (pass rate strictly between 0 and 1)")
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    Path(args.figure).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.figure, dpi=140)


if __name__ == "__main__":
    main()
