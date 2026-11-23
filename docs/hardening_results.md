# Statistical hardening of the cells that decide the ordering

Eighth follow-up. Pre-registered in [hardening_prereg.md](hardening_prereg.md) (written before the new runs). Builds on [combo_results.md](combo_results.md), which found run-to-run differences of up to 0.095 in doc SLO between two effective replicates of one configuration. Same host, stack, model, SLOs (chat TTFT <= 1 s, doc <= 3 s, TPOT <= 100 ms), B2, `max_num_batched_tokens` 8192. 48 new runs: 4 more repeats (r3 to r6, fixed-seed random order per block) for each of 12 cells (3 configurations x 4 decisive cells), for 6 runs per cell. Data: `results/real/hardening_analysis.json`, raw `results/raw/*-r[3-6].*`, `results/raw/gateway_hard_runs.jsonl`, figure `results/figures/hardening/decisive_cells.png`; analysis `python -m cacheflow.stats_analyze`.

Method: the unit is the run. Per-run attainment per class; a cell's value is the mean of its 6 runs; intervals are bootstrap over the runs (10,000 resamples); a cell passes when mean chat >= 0.95 and mean doc >= 0.90; "P(pass)" is the share of resamples in which it passes (a bootstrap summary, not a Bayesian probability).

## Results (6 runs per cell)

| Seed, level | Config | Chat mean [95% CI] | Doc mean [95% CI] | Run SD chat / doc | Pass | P(pass) |
|---|---|---|---|---|---|---|
| 7, mid45 | gateway chat-first | 0.942 [0.919, 0.961] | 0.825 [0.813, 0.841] | 0.027 / 0.019 | fail | 0.00 |
| 7, mid45 | + demotion | 0.928 [0.911, 0.947] | 0.929 [0.917, 0.940] | 0.025 / 0.015 | fail | 0.02 |
| 7, mid45 | engine priority | 0.986 [0.983, 0.992] | 0.877 [0.853, 0.909] | 0.007 / 0.041 | fail | 0.09 |
| 23, mid45 | gateway chat-first | 1.000 [1.000, 1.000] | 0.869 [0.857, 0.885] | 0.000 / 0.020 | fail | 0.00 |
| 23, mid45 | + demotion | 0.983 [0.972, 0.994] | 0.933 [0.921, 0.944] | 0.018 / 0.018 | **pass** | 1.00 |
| 23, mid45 | engine priority | 0.961 [0.942, 0.981] | 0.917 [0.893, 0.940] | 0.027 / 0.033 | **pass** | 0.83 |
| 11, mid42 | gateway chat-first | 0.956 [0.942, 0.969] | 0.964 [0.948, 0.976] | 0.020 / 0.020 | **pass** | 0.81 |
| 11, mid42 | + demotion | 0.956 [0.944, 0.969] | 0.956 [0.952, 0.964] | 0.017 / 0.010 | **pass** | 0.86 |
| 11, mid42 | engine priority | 1.000 [1.000, 1.000] | 0.968 [0.948, 0.984] | 0.000 / 0.025 | **pass** | 1.00 |
| 11, burst | gateway chat-first | 0.986 [0.983, 0.992] | 0.841 [0.813, 0.869] | 0.007 / 0.039 | fail | 0.00 |
| 11, burst | + demotion | 0.983 [0.969, 0.994] | 0.921 [0.913, 0.929] | 0.018 / 0.012 | **pass** | 1.00 |
| 11, burst | engine priority | 0.986 [0.983, 0.992] | 0.833 [0.810, 0.857] | 0.007 / 0.034 | fail | 0.00 |

Passes over the 4 decisive cells: gateway chat-first 1, chat-first + demotion 3, engine priority 2.

## Hypotheses against outcomes

- **H1 (engine priority passes >= 2 of 4 cells and more than gateway chat-first): met, narrowly** (2 vs 1). At the level of load levels, which is the claim that mattered for the earlier headline, it is weaker: engine priority passes a strictly heavier level than gateway chat-first on **1 of 3 seeds** (seed 23, mid45), ties on seed 7 (both pass mid50, both fail mid45) and on seed 11 (both pass mid42, both fail burst). The earlier pre-registered R2 (heavier on at least 2 of 3 seeds, study 7) is therefore **no longer met**.
- **H2 (demotion passes at least as many cells as engine priority): met** (3 vs 2).
- **H3 (doc run-to-run SD >= 0.03 in at least 6 of the 12 cells): not met** (4 of 12). Noise depends on the configuration: doc SD is 0.010 to 0.018 for demotion, 0.019 to 0.039 for gateway chat-first and 0.025 to 0.041 for engine priority.
- **H4 (descriptive; intervals of the difference of means excluding 0 on at least one class):** gateway chat-first to engine priority in 3 of 4 cells (seed 7: chat +0.044 [+0.025, +0.067], doc +0.052 [+0.024, +0.087]; seed 23: chat -0.039 [-0.058, -0.019], doc +0.048 [+0.020, +0.075]; seed 11 mid42: chat +0.044 [+0.031, +0.058]; seed 11 burst: neither). Engine priority to demotion in 3 of 4 cells (seed 7 mid45: chat -0.058, doc +0.052; seed 11 mid42: chat -0.044; seed 11 burst: doc +0.087 [+0.060, +0.111]).

## What the data support

1. **The seed-7 headline did not survive.** With 6 runs, engine priority at seed 7 mid45 is 0.986 / 0.877 (P(pass) 0.09), not the 0.99 / 0.92 of the first two runs. All three configurations tie at mid50 on seed 7, so the capacity ladder on seed 7 is 4.0 (B1) to 5.5 (B2) to 5.5 (B2 8192 FIFO) to **6.9 req/s** (chat-first, demotion and engine priority alike): **1.7x over B1, not 1.9x**.
2. **Engine priority improves attainment, but not reliably enough to pass a heavier level.** It is better than gateway chat-first on both classes at seed 7 mid45 and on doc at seed 23 mid45, and better on chat at seed 11 mid42, but worse on chat at seed 23 mid45 (0.961 vs 1.000); it passes a heavier level on one seed.
3. **Chat-first + demotion is the most consistent configuration in these cells:** it passes 3 of 4, with the highest pass probabilities (0.86 to 1.00), the smallest run-to-run spread, and it is the only one that passes seed 11 burst (doc 0.921 vs 0.833 for engine priority, interval excludes 0). Its remaining miss is chat at seed 7 mid45 (0.928).
4. **Run-to-run noise is configuration-dependent**, largest for engine priority (doc SD up to 0.041) and smallest for demotion (0.010 to 0.018). The cause was not investigated.
5. **Pass/fail at two repeats flips and then reverses:** seed 11 mid42 gateway chat-first failed with 2 runs (chat 0.933) and passes with 6 (0.956); seed 7 mid45 engine priority passed with 2 runs and fails with 6.

## Limitations

- Six runs per cell, and only for 12 cells; the rest of the capacity ladder still rests on two runs per cell. Intervals from 6 runs are themselves uncertain.
- The four cells were chosen because earlier results were near thresholds; they are the most noise-sensitive cells, so they are not representative of all cells, and earlier values for them may have been selected favourably.
- P(pass) is a bootstrap summary of 6 values and should not be read as a probability of passing in production.
- Results are for one host, one 1.7B model, three document sets and simulated arrivals; the run order was randomized within blocks, but host drift across the roughly one hour of runs was not separately measured (mean attainment of r1 and r2 versus r3 to r6 is stored per cell in the JSON; averaged over the 12 cells the difference is -0.007 for chat and -0.001 for doc, mean absolute 0.014 and 0.018, so there is no systematic drift, with the largest shifts for engine priority: seed 7 mid45 doc -0.060 and seed 23 mid45 chat -0.046).

## Reproduce (from `/workspace`)

```bash
# 48 runs: for each repeat k in 3..6, the 12 cells below in a fixed-seed random order (see the driver listing in docs/hardening_prereg.md for the design);
# cells: (seed 7, mid45), (seed 23, mid45), (seed 11, mid42), (seed 11, burst) x configs B2TP, B2TD, B2TV; one run per call, e.g.
TRACE_PREFIX=s11 RUN_PREFIX=s11 REGISTRY=/workspace/results/s11_registry.csv bash scripts/run_real_workload.sh "B2TD burst r3"
# offline analysis from the committed raw files
PYTHONPATH=src python -m cacheflow.stats_analyze
```
