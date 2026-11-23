# Replication on a new seed, and a slack-based admission policy

Third follow-up. Hypotheses were fixed before the runs in [replication_slack_prereg.md](replication_slack_prereg.md). Builds on [policy_study_results.md](policy_study_results.md). Same host (RTX 3090), stack, model, SLOs (chat TTFT <= 1 s, doc <= 3 s, TPOT <= 100 ms). 18 runs executed 2026-11-23 host time. Data: `results/real60_registry.csv`, `results/s11_registry.csv`, `results/real/slack_analysis.json`, `results/real/s11_analysis.json`, raw `results/raw/r60-mid45*`, `r60-*-b2ts*`, `s11-*`, figures in `results/figures/slack_study/` and `results/figures/replication_seed11/`.

## Experiment 1: does the chat-first result hold on a different document set?

New traces with `--seed 11` (14 other QuALITY documents, 6,015 to 8,339 tokens; 60 other ShareGPT chats; same filters, profiles and output budgets; trace hashes in `results/real/s11_*.manifest.json`). B2, 8192, FIFO vs chat-first, loads mid50 and burst, 2 repeats, reversed order on repeat 2.

| Seed | Load | Policy | Chat p95 (s) | Chat SLO | Doc p95 (s) | Doc SLO | Goodput (req/s) |
|---|---|---|---|---|---|---|---|
| 7 | mid50 | FIFO | 1.85 | 0.68 | 1.92 | 1.00 | 5.20 |
| 7 | mid50 | chat-first | 0.85 | 0.98 | 2.58 | 1.00 | 6.33 |
| 11 | mid50 | FIFO | 0.97 | 0.97 | 1.09 | 1.00 | 6.23 |
| 11 | mid50 | chat-first | 0.58 | 1.00 | 1.53 | 1.00 | 6.39 |
| 7 | burst | FIFO | 3.02 | 0.30 | 3.31 | 0.88 | 4.06 |
| 7 | burst | chat-first | 0.97 | 0.94 | 4.61 | 0.69 | 6.44 |
| 11 | burst | FIFO | 2.24 | 0.47 | 2.52 | 1.00 | 5.39 |
| 11 | burst | chat-first | 0.80 | 0.99 | 3.52 | 0.83 | 7.27 |

Paired differences on seed 11 (chat-first minus FIFO, 95% bootstrap CI over request IDs): mid50 chat SLO +0.03 [+0.01, +0.07], doc SLO 0.00; burst chat SLO +0.53 [+0.40, +0.65], doc SLO -0.17 [-0.27, -0.07].

- **R1 (mid50): partly.** Chat-first keeps both classes on target (chat 1.00, doc 1.00), as predicted. The other half of R1, that FIFO misses the chat target, did not hold: on this document set FIFO already gives chat 0.97. At the same nominal spacing seed 11 is a lighter load (FIFO doc p95 1.09 s vs 1.92 s; the cause was not isolated: document set, chat prompts and visit order all differ).
- **R2 (burst): supported.** Neither policy reaches both targets (FIFO 0.47 / 1.00, chat-first 0.99 / 0.83, chat / doc), the same shape as seed 7: chat-first buys a large chat gain (+0.53) and pays with doc attainment (-0.17).

What replicates: direction and rough size of the chat-first effect at saturation (chat SLO +0.64 on seed 7, +0.53 on seed 11; doc SLO -0.19 and -0.17). What does not transfer: the load at which FIFO breaks. The spacing of first visits is therefore a convenient knob but not a capacity measure; "mid50 is where chat-first is free" is specific to seed 7, and on seed 11 the same spacing does not stress FIFO.

## Experiment 2: slack-based admission (`class_slack`)

Policy (fixed before the runs): chat first; a doc is promoted once `waited >= 3000 ms - 72 ms/1k tokens x prompt_tokens - 500 ms` (about 2.0 s for a 7K-token doc). Seed 7 traces, B2, 8192, 2 repeats per cell; new load mid45 (first visits every 0.45 s). FIFO / chat-first / age-cap cells at mid50 and burst are from the previous study.

| Load | Policy | Chat p95 (s) | Chat SLO | Doc p95 (s) | Doc SLO | Goodput | Docs promoted per run |
|---|---|---|---|---|---|---|---|
| mid50 | FIFO | 1.85 | 0.68 | 1.92 | 1.00 | 5.20 | - |
| mid50 | chat-first | 0.85 | 0.98 | 2.58 | 1.00 | 6.33 | - |
| mid50 | age cap 1.5 s | 1.75 | 0.84 | 2.15 | 1.00 | 5.79 | 10, 10 |
| mid50 | **slack** | 1.09 | 0.92 | 2.38 | 1.00 | 6.07 | 6, 6 |
| mid45 | FIFO | 2.38 | 0.57 | 2.43 | 1.00 | 5.22 | - |
| mid45 | chat-first | 1.08 | 0.94 | 3.54 | 0.83 | 6.22 | - |
| mid45 | **slack** | 1.93 | 0.78 | 2.98 | 0.95 | 5.90 | 11, 11 |
| burst | FIFO | 3.02 | 0.30 | 3.31 | 0.88 | 4.06 | - |
| burst | chat-first | 0.97 | 0.94 | 4.61 | 0.69 | 6.44 | - |
| burst | age cap 1.5 s | 3.07 | 0.53 | 3.32 | 0.85 | 5.00 | 22, 25 |
| burst | **slack** | 3.10 | 0.53 | 3.34 | 0.75 | 4.63 | 22, 23 |

Selected paired differences (slack minus other; 95% CI): mid45 vs chat-first chat SLO -0.17 [-0.27, -0.08], doc SLO +0.12 [+0.02, +0.24]; mid45 vs FIFO chat SLO +0.20 [+0.10, +0.31], doc SLO -0.05 [-0.12, 0.00]; mid50 vs chat-first chat SLO -0.07 [-0.13, -0.02]; burst vs chat-first doc SLO +0.06 [+0.01, +0.12], chat SLO -0.41 [-0.52, -0.29].

- **S1 (mid45): not supported.** No policy reaches both targets: FIFO 0.57 / 1.00, chat-first 0.94 / 0.83, slack 0.78 / 0.95 (chat / doc). Slack lands between the two. The three points are one trade-off curve rather than a window; slack's doc attainment (0.95) is higher than a straight line between FIFO and chat-first would give at chat 0.78 (about 0.90), but that is two runs and I do not claim a better frontier.
- **S2 (mid50): not supported.** Slack gives chat 0.92, 0.07 below chat-first (CI [-0.13, -0.02]), more than the 0.03 allowed, and misses the 0.95 chat target that chat-first meets. Doc stays at 1.00. So slack gives up the free case, because it promotes 6 docs per run ahead of chat that did not need to go first (all docs met their SLO anyway).
- **S3 (burst): supported.** Slack does not reach both targets (0.53 / 0.75); at burst it is not better than the 1.5 s age cap (0.53 / 0.85) on doc and equal on chat.

## What the data support

1. **Under the load range tested, no admission order tried beats plain chat-first on both classes, and no order closes the gap at saturation.** The relevant range is narrow: chat-first alone is enough where docs have slack (seed 7 mid50), and at higher load every order only moves misses between classes.
2. **Promoting docs by slack (or age) costs chat attainment before it saves doc attainment.** At mid50 neither promotion rule was needed and each cost chat SLO (age cap 0.84, slack 0.92 vs 0.98). A margin of 500 ms plus an `est_service` that is deliberately a full-prefill estimate (it overstates the cost of cache hits, which dominate q1/q2 visits) makes promotion trigger earlier than the doc's actual need; I did not test a margin or estimate that reflects cache hits.
3. **The chat-first effect at saturation replicates on a second document set** (chat SLO +0.53 to +0.64; doc SLO -0.17 to -0.19); the load level at which it becomes necessary does not transfer.

## Limitations

- Two document sets (seed 7, seed 11), one host, one model; arrival times simulated. Two repeats per cell; request-level bootstrap intervals understate run-to-run variance. Seed 11 has only FIFO and chat-first cells at mid50 and burst; the promotion policies were not run on it.
- `class_slack` was run with one parameter set (margin 500 ms, 72 ms/1k tokens, SLO 3000 ms) fixed in advance. A different margin, or an estimate that knows about cache hits (the gateway could compare prefix blocks with its recent history), may behave differently. This experiment cannot say.
- mid45 is one extra load point; there is no measured capacity, so "no window" means none was found at the points tried.
- Chat-first keys on a client-declared class header at the gateway; vLLM's own priority scheduling was not tested.

## Reproduce (from `/workspace`)

```bash
PYTHONPATH=src /venv/main/bin/python -m cacheflow.real_workload --model-path <Qwen3-1.7B snapshot> --prefix real60 --chats 60            # adds mid45
PYTHONPATH=src /venv/main/bin/python -m cacheflow.real_workload --model-path <snapshot> --prefix s11 --seed 11 --chats 60
export TRACE_PREFIX=real60 RUN_PREFIX=r60 REGISTRY=/workspace/results/real60_registry.csv
bash scripts/run_real_workload.sh "B2T mid45 r1" "B2TP mid45 r1" "B2TS mid45 r1" "B2TS mid45 r2" "B2TP mid45 r2" "B2T mid45 r2" \
  "B2TS mid50 r1" "B2TS burst r1" "B2TS burst r2" "B2TS mid50 r2"
export TRACE_PREFIX=s11 RUN_PREFIX=s11 REGISTRY=/workspace/results/s11_registry.csv
bash scripts/run_real_workload.sh "B2T mid50 r1" "B2TP mid50 r1" "B2T burst r1" "B2TP burst r1" "B2TP mid50 r2" "B2T mid50 r2" "B2TP burst r2" "B2T burst r2"
PYTHONPATH=src python -m cacheflow.policy_analyze --gateway results/raw/gateway_r60_runs.jsonl results/raw/gateway_policy_runs.jsonl results/raw/gateway_slack_s11_runs.jsonl \
  --summary-json results/real/slack_analysis.json --out-dir results/figures/slack_study
PYTHONPATH=src python -m cacheflow.policy_analyze --registry results/s11_registry.csv --run-prefix s11 --gateway results/raw/gateway_slack_s11_runs.jsonl \
  --summary-json results/real/s11_analysis.json --out-dir results/figures/replication_seed11
```

Config letters: `T` = 8192, `P` = chat-first, `A` = age cap, `S` = slack promotion.
