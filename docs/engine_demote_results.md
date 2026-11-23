# Demotion order inside vLLM's own waiting queue

Study 12. Pre-registered in [engine_demote_prereg.md](engine_demote_prereg.md) (hypotheses E1 to E4 before the main runs; the capacity-ladder addendum P1 to P3 after E1 to E4 were met and before its runs). Fills the missing corner of the decomposition in [locus_results.md](locus_results.md). Same host, stack, model and SLOs (chat TTFT <= 1 s, doc <= 3 s, TPOT <= 100 ms), B2, `max_num_batched_tokens` 8192; 48 runs (24 on the four decisive cells x 6, 24 on the ladder check), random order within repeat blocks. Data: `results/real/locus_analysis.json`, raw `results/raw/*b2tve-*`, `results/raw/gateway_edemote_runs.jsonl`; analysis `python -m cacheflow.locus_analyze`; the patch is `scripts/patch_vllm_engine_demote.py`.

## What was changed in vLLM

A patch of about 60 lines to `vllm/v1/core/sched/request_queue.py` (vLLM 0.22.0), active only when the environment variable `CACHEFLOW_ENGINE_DEMOTE=1` is set (otherwise vLLM's unmodified queue is used; a unit test on the host checks both modes). With `--scheduling-policy priority`, the waiting queue then picks the next request by (tier, priority, arrival time): tier 0 for chat (priority 0), tier 1 for documents that can still meet a 3 s TTFT SLO, tier 2 for documents that are already doomed, meaning `(now - arrival_time) + 72 ms per 1,000 prompt tokens > 3 s`. Doomed documents are still served, after everything else. The request returned by `peek` is the one `pop` removes. Everything else is as in engine priority (B2TV): chat priority 0, documents priority 1 (set by the client), a pass-through gateway with 64 in flight, `max_num_seqs` 16. The engine rule has no prefix-cache discount (the engine cannot see a prefix hit before scheduling), so cached second and third visits are demoted about 0.35 s earlier than by the gateway rule.

## Results on the four decisive cells (6 runs each)

| Series | Document queue | Order | Cells passed | Mean chat | Mean doc | Doc run SD | Design effect [95% CI] |
|---|---|---|---|---|---|---|---|
| V engine priority | engine | FIFO | 2 of 4 | 0.983 | 0.899 | 0.033 | 1.94 [1.12, 2.45] |
| **E engine priority + demotion in the engine queue** | engine | demotion | **4 of 4** | 0.983 | **0.938** | 0.020 | **0.59** [0.29, 1.04] |
| D chat-first + demotion (gateway) | gateway | demotion | 3 of 4 | 0.963 | 0.935 | 0.014 | 0.30 [0.14, 0.61] |
| P gateway chat-first | gateway | FIFO | 1 of 4 | 0.971 | 0.875 | 0.025 | 1.26 [0.72, 1.77] |

Per cell (chat / doc attainment; pass = chat >= 0.95 and doc >= 0.90):

| Cell | engine priority (V) | chat-first + demotion (D) | **engine priority + demotion (E)** |
|---|---|---|---|
| seed 7, mid45 | 0.986 / 0.877 fail | 0.928 / 0.929 fail | **0.989 / 0.933 pass** |
| seed 23, mid45 | 0.961 / 0.917 pass | 0.983 / 0.933 pass | 0.961 / 0.940 pass |
| seed 11, mid42 | 1.000 / 0.968 pass | 0.956 / 0.956 pass | 1.000 / 0.952 pass |
| seed 11, burst | 0.986 / 0.833 fail | 0.983 / 0.921 pass | 0.983 / 0.925 pass |

- **E1 (design effect <= 1.0): met** (0.59). **E2 (chat >= 0.97 and doc >= 0.92): met** (0.983, 0.938). **E3 (passes >= 3 of 4 cells): met** (4 of 4). **E4 (SD of the number of document misses per run smaller than for engine priority in >= 3 of 4 cells): met in 4 of 4** (1.17, 0.84, 0.63, 0.75 against 1.72, 1.38, 1.03, 1.41).
- **This completes the 2 x 2 design.** The document outcomes are decorrelated by the demotion order whichever queue it acts in: engine queue (FIFO 1.94, demotion 0.59) and gateway queue (FIFO 1.26 to 1.65, demotion 0.30 to 0.77). Queue location is not the factor; the ordering is.
- **It is the first configuration that meets both targets in all four decisive cells**, keeping engine priority's chat attainment (0.983) and gaining the demotion order's document attainment (0.938 against 0.899 for engine priority; 0.935 for gateway demotion, which pays in chat: 0.963).
- Costs: documents that are demoted wait longer, so the document p95 TTFT rises from 3.39 to 4.25 s at seed 7 mid45 and from 3.45 to 4.22 s at seed 11 burst, and is unchanged at seed 23 mid45 (3.42 vs 3.33 s) and seed 11 mid42 (2.91 vs 2.97 s); goodput is about unchanged (6.73 vs 6.55 req/s at seed 7 mid45, 7.54 vs 7.25 at seed 11 burst).

## Capacity-ladder check (addendum P1 to P3; seeds 7 and 23, 4 runs per new cell)

| Cell | Runs | Chat | Doc | Pass |
|---|---|---|---|---|
| seed 7, mid50 (6.9 req/s) | 4 | 1.000 | 0.994 | pass |
| seed 7, mid45 (7.6) | 6 | 0.989 | 0.933 | pass |
| seed 7, mid42 (8.2) | 4 | 0.992 | 0.893 | fail |
| seed 7, burst (8.6) | 4 | 0.958 | 0.839 | fail |
| seed 23, mid50 | 4 | 1.000 | 1.000 | pass |
| seed 23, mid45 | 6 | 0.961 | 0.940 | pass |
| seed 23, mid42 | 4 | 0.958 | 0.857 | fail |
| seed 23, burst | 4 | 0.925 | 0.798 | fail |
| seed 11, mid42 / burst | 6 | 1.00 / 0.983 | 0.952 / 0.925 | pass / pass |

- **P1 (strictly heavier level than all three others on >= 2 of 3 seeds): not met.** Heaviest pass: seed 7 mid45 (7.6 req/s) against mid50 (6.9) for the others (+10%); seed 23 mid45, the same as demotion and engine priority (tie); seed 11 burst, the same as gateway demotion (tie, top of the grid). So the gain in capacity is on one seed.
- **P2 (seed 23 passes mid42): not met** (0.958 / 0.857).
- **P3 (no harm at mid50): met** on both seeds.
- Net: the benefit of this configuration is **robustness at the loads where the others are marginal** (4 of 4 decisive cells, spread cut by a third to a half), not a broad shift of the capacity ladder (document run SD 0.020 against 0.033 for engine priority).

## What the data support

1. **The demotion order is the factor that decorrelates the document outcomes, in either queue**, which closes the missing corner of the decomposition and supports the mechanism read directly from the gateway flag ([locus_results.md](locus_results.md)): an early, deadline-based classification of documents that cannot make it insulates the ones that can.
2. **A deadline-aware ordering in vLLM's own waiting queue, in about 60 lines, gives the most robust configuration tested** while keeping the chat attainment of engine-level priority; it does not need a gateway cap.
3. **It does not lift the capacity ladder broadly** (+10% on one seed, ties elsewhere, fails at 8.2 req/s on both seeds where it was checked).

## Limitations

- Four decisive cells (6 runs each) plus ladder cells with 4 runs; one host and a 1.7B model. The design-effect interval of E (0.29 to 1.04) touches 1.0.
- The patch is research code: an O(n) scan per `peek` (the waiting queue holds fewer than about 100 requests here), no interaction with preemption was studied, and arrival time is the engine's receipt time (about 20 ms after the scheduled arrival).
- The engine rule differs from the gateway rule (no prefix discount); its classifier was not traced per request as the gateway's was (the engine has no per-request flag in these runs), so the mechanism in the engine queue is supported by the outcome statistics (design effect, miss-count SD) and not by a direct flag trace.
- The check at heavier loads used 4 runs per cell; the failed cells are near the thresholds (seed 7 mid42 doc 0.893).

## Reproduce (from `/workspace`)

```bash
python scripts/patch_vllm_engine_demote.py      # once per host; idempotent; keeps a .orig backup
# 24 decisive-cell runs (4 cells x repeats 1 to 6) and 24 ladder-check runs (seeds 7 and 23, mid50 / mid42 / burst, repeats 1 to 4), one run per call, e.g.
TRACE_PREFIX=s11 RUN_PREFIX=s11 REGISTRY=/workspace/results/s11_registry.csv bash scripts/run_real_workload.sh "B2TVE burst r1"
PYTHONPATH=src python -m cacheflow.locus_analyze
```

Config letter `VE` = engine priority + deadline-aware demotion inside vLLM's waiting queue (`CACHEFLOW_ENGINE_DEMOTE=1`).
