# Demoting doomed documents (`class_demote`)

Fourth follow-up; hypotheses fixed before the runs in [demotion_prereg.md](demotion_prereg.md). Builds on [replication_slack_results.md](replication_slack_results.md). Same host, model, SLOs (chat TTFT <= 1 s, doc <= 3 s, TPOT <= 100 ms), B2, `max_num_batched_tokens` 8192. 10 new runs (2 repeats per cell, reversed order on repeat 2). Data: `results/real60_registry.csv`, `results/s11_registry.csv`, `results/real/demote_analysis.json`, `results/real/s11_demote_analysis.json`, raw `results/raw/*b2td*`, figures `results/figures/demotion_study/`, `demotion_seed11/`.

## Policy

Chat first; a document that cannot meet its SLO even if admitted immediately (`waited + est_service > 3000 ms`; `est_service` = 150 ms on a recent prefix match, else 72 ms per 1,000 prompt tokens) goes to a best-effort tier served after everything else. Demoted documents are still served, never rejected; attainment is counted over all offered requests. Chat is never demoted. It is the signal `class_slack` used to promote, with the opposite action; no parameter was tuned.

## Results (two runs per cell; chat SLO / doc SLO)

| Seed | Load | FIFO | chat-first | slack promotion | **demotion** | Docs demoted per run | Demoted docs that still met SLO |
|---|---|---|---|---|---|---|---|
| 7 | mid50 | 0.68 / 1.00 | 0.98 / 1.00 | 0.92 / 1.00 | 0.96 / 0.99 | 0, 2 | 1 of 2 |
| 7 | mid45 | 0.57 / 1.00 | 0.94 / 0.83 | 0.78 / 0.95 | **0.94 / 0.94** | 3, 2 | 0 of 5 |
| 7 | burst | 0.30 / 0.88 | 0.94 / 0.69 | 0.53 / 0.75 | 0.89 / 0.79 | 7, 7 | 0 of 14 |
| 11 | mid50 | 0.97 / 1.00 | 1.00 / 1.00 | - | 1.00 / 1.00 | 0, 0 | - |
| 11 | burst | 0.47 / 1.00 | 0.99 / 0.83 | - | **0.99 / 0.92** | 3, 4 | 0 of 7 |

Paired differences against chat-first (95% bootstrap CI over request IDs): seed 7 burst chat -0.050 [-0.092, -0.017], doc +0.095 [+0.024, +0.179]; seed 7 mid45 chat 0.000, doc +0.107 [+0.024, +0.214]; seed 11 burst chat 0.000, doc +0.083 [+0.024, +0.143].

Other per-cell facts (demotion vs chat-first): computed prefill tokens identical (seed 7 burst 104,715 vs 104,603; seed 11 burst 89,489 vs 89,489); goodput 6.44 vs 6.44 (seed 7 burst), 6.57 vs 6.22 (seed 7 mid45), 7.57 vs 7.27 (seed 11 burst); doc TTFT median 2,073 to 1,518 ms and p95 4,612 to 7,473 ms (seed 7 burst), doc p95 3,537 to 4,836 ms (mid45), 3,517 to 4,492 ms (seed 11 burst). Of the 14 demoted docs in seed 7 burst runs, 5 were first visits and 9 were revisits (cache hits).

## Hypotheses against outcomes

- **D1** (seed 7 burst: doc SLO up by at least 0.10, chat down by at most 0.05): **not met, by a small margin.** Doc SLO +0.095 (below 0.10), chat -0.050 (right at the limit). Per the pre-registration the headline "demotion recovers doc SLO at saturation" is dropped for this cell.
- **D2** (seed 7 mid45: both classes >= 0.90): **met.** 0.94 / 0.94 (chat-first 0.94 / 0.83).
- **D3** (seed 7 mid50: neither class changes by more than 0.03): **met.** Chat -0.025, doc -0.012; two documents were demoted in one run.
- **D4** (seed 11 burst: doc up by at least 0.05, chat down by at most 0.05): **met.** Doc +0.083, chat 0.000.

## What the data support

1. **A small, consistent effect on the document class, mostly at no chat cost.** At mid45 and on seed 11 burst demotion raises doc SLO by 0.08 to 0.11 with chat unchanged; at seed 7 burst it trades 0.05 chat for 0.095 doc (about 3 chat requests for 4 doc requests per run; net attained requests per run +1.0).
2. **It does not add capacity.** Computed prefill tokens are unchanged because demoted documents are still served, and goodput changes by 0% (seed 7 burst) to +6% (mid45, seed 11 burst). The 33% "compute spent on documents that miss anyway" seen in the earlier data is not recovered by demotion; only dropping those requests would save it, and dropping a first visit also forfeits the cache benefit for its later revisits (not tested).
3. **The mechanism is reordering toward savable documents.** The doomed rule picked its targets accurately: 0 of 26 demoted documents at mid45 and burst still met the SLO (1 of 2 at mid50), and 14 of the 18 documents that missed in seed 7 burst were demoted ones. Median doc TTFT falls (2.07 s to 1.52 s in seed 7 burst) while the tail grows (p95 4.6 s to 7.5 s): the cost is paid by the documents that were going to miss anyway, who now wait up to 8 s.
4. **Among the policies tried, demotion has the best doc/chat balance at mid45.** At mid45 it matches chat-first on chat (0.94) and is above it on doc (0.94 vs 0.83); slack promotion (0.78 / 0.95) and the 1.5 s age cap are worse on chat. No policy reached chat >= 0.95 and doc >= 0.90 at mid45 (demotion misses the chat target by 0.01).

## Limitations

- Two document sets, one host and model, simulated arrivals, 2 repeats per cell; intervals ignore run-to-run variance. A threshold decided in advance (D1) was missed by 0.005; I report it as missed.
- Demotion changes who waits, not how much work is done; products that cannot tolerate 7 to 8 s tails for the demoted class need a different fallback (rejection, a smaller model), which this experiment does not evaluate.
- The service-time estimates (150 ms hit, 72 ms per 1K tokens) came from earlier measurements on this host and ignore contention; the recent-prefix test is a proxy for a cache hit. No sensitivity to these values was run.
- The same comparator cells (FIFO, chat-first) come from earlier runs with the same traces; code differs only by added policies.
- Seed 11 has no mid45 cell with demotion.

## Reproduce (from `/workspace`)

```bash
export TRACE_PREFIX=real60 RUN_PREFIX=r60 REGISTRY=/workspace/results/real60_registry.csv
bash scripts/run_real_workload.sh "B2TD mid50 r1" "B2TD mid45 r1" "B2TD burst r1" "B2TD burst r2" "B2TD mid45 r2" "B2TD mid50 r2"
export TRACE_PREFIX=s11 RUN_PREFIX=s11 REGISTRY=/workspace/results/s11_registry.csv
bash scripts/run_real_workload.sh "B2TD mid50 r1" "B2TD burst r1" "B2TD burst r2" "B2TD mid50 r2"
PYTHONPATH=src python -m cacheflow.policy_analyze --gateway results/raw/gateway_r60_runs.jsonl results/raw/gateway_policy_runs.jsonl \
  results/raw/gateway_slack_s11_runs.jsonl results/raw/gateway_demote_runs.jsonl --summary-json results/real/demote_analysis.json --out-dir results/figures/demotion_study
PYTHONPATH=src python -m cacheflow.policy_analyze --registry results/s11_registry.csv --run-prefix s11 \
  --gateway results/raw/gateway_slack_s11_runs.jsonl results/raw/gateway_demote_runs.jsonl --summary-json results/real/s11_demote_analysis.json --out-dir results/figures/demotion_seed11
```

Config letter `D` = chat-first with doomed-document demotion.
