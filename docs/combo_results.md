# Engine-level priority combined with doomed-document demotion

Seventh follow-up. Hypotheses C1 to C4 and the attempt 2 design are in [combo_prereg.md](combo_prereg.md) (the attempt 2 addendum was written after attempt 1 and before the attempt 2 runs; it is marked there). Builds on [robustness_mechanism_results.md](robustness_mechanism_results.md). Same host, stack, model, SLOs (chat TTFT <= 1 s, doc <= 3 s, TPOT <= 100 ms), B2, `max_num_batched_tokens` 8192, 2 repeats per cell with reversed order on repeat 2; 40 new runs (20 per attempt). Data: `results/real/combo_summary_attempt{1,2}.json`, `results/real/capacity_seed{7,11,23}.json`, raw `results/raw/*b2tvd-*` (attempt 1) and `*b2tvd4-*` (attempt 2), `results/raw/gateway_combo{,4}_runs.jsonl`.

## Design

Policy `engine_demote`: chat bypasses the gateway's in-flight cap and goes straight to vLLM, whose `--scheduling-policy priority` (chat 0, doc 1, set by the client) orders it ahead of waiting documents; documents are capped at N in flight at the gateway and admitted in demotion order (a document with `waited + expected service > 3000 ms` goes last, still served). Expected service is 150 ms on a recent prefix match, else 72 ms per 1,000 prompt tokens, as in `class_demote`. Attempt 1: N = 16 (config `B2TVD`). Attempt 2: N = 4 (config `B2TVD4`). Cells: seeds 7, 11 and 23 at mid45, mid42 and burst, plus mid50 on seed 7.

## Attempt 1 did not bind, and what that revealed

Evaluated with the pre-registered rules, attempt 1 failed C1 and C2 (0 of 3 seeds heavier than the better parent) and C4 (0 of 4 complementary cells), and met C3. A diagnostic showed why: with 42 document requests per trace the cap of 16 almost never bound, documents' gateway wait was 16 to 21 ms (same as engine priority alone), and all queueing happened in vLLM's waiting queue, where the demotion order has no effect (document engine segment mean 1.2 to 2.4 s, versus 0.34 to 0.43 s under gateway demotion). Attempt 1 is therefore effectively a **second replicate of engine priority** (B2TV), not a test of the combination.

That makes it useful for something else: the run-to-run noise of one configuration. Across the 10 cells (seeds 7, 11, 23; B2TV vs its replicate), the difference in attainment was:

| | mean absolute difference | max |
|---|---|---|
| chat SLO | 0.008 | 0.025 |
| doc SLO | **0.035** | **0.095** |

Cells near a threshold flip between replicates: seed 7 mid45 doc 0.917 vs 0.869; seed 23 mid45 doc 0.893 vs 0.940; seed 23 burst doc 0.643 vs 0.738. Pooling the four runs of the two replicates (a post hoc computation, equal weights) gives: seed 7 mid45 0.992 / 0.893 (fail), seed 23 mid45 0.983 / 0.917 (pass), seed 11 mid42 pass, seed 11 mid45 pass. **The earlier statement "engine priority passes a heavier level than gateway chat-first on seed 7" rested on a single replicate that did not reproduce; on the pooled data it ties at mid50 on seed 7 and passes a heavier level on seeds 11 and 23.** The count "2 of 3 seeds" survives, but the seeds that carry it change with the replicate.

## Attempt 2: a binding document cap

The cap of 4 was fixed by a rule from earlier data (median over the 18 earlier gateway-demotion runs at mid45, mid42 and burst of the time-averaged number of documents in flight, 4.3), not from any B2TVD result. Chat / doc SLO attainment; `*` = pass (chat >= 0.95 and doc >= 0.90):

| Seed | Level | B2TP (gateway chat-first) | B2TD (gateway demotion) | B2TV (engine priority) | **B2TVD4** |
|---|---|---|---|---|---|
| 7 | mid50 | 0.98 / 1.00 * | 0.96 / 0.99 * | 1.00 / 1.00 * | 1.00 / 0.95 * |
| 7 | mid45 | 0.94 / 0.83 | 0.94 / 0.94 | 0.99 / 0.92 * | 1.00 / 0.86 |
| 7 | mid42 | 0.93 / 0.75 | 0.90 / 0.86 | 1.00 / 0.74 | 0.99 / 0.87 |
| 7 | burst | 0.94 / 0.69 | 0.89 / 0.79 | 0.98 / 0.71 | 0.98 / 0.79 |
| 11 | mid45 | 1.00 / 1.00 * | 1.00 / 1.00 * | 1.00 / 1.00 * | 1.00 / 0.95 * |
| 11 | mid42 | 0.93 / 0.96 | 0.97 / 0.95 * | 1.00 / 0.99 * | 1.00 / 0.94 * |
| 11 | burst | 0.99 / 0.83 | 0.99 / 0.92 * | 0.98 / 0.81 | 1.00 / 0.86 |
| 23 | mid45 | 1.00 / 0.87 | 0.98 / 0.93 * | 0.99 / 0.89 | 0.99 / 0.89 |
| 23 | mid42 | 0.94 / 0.80 | 0.94 / 0.87 | 0.93 / 0.76 | 0.99 / 0.82 |
| 23 | burst | 0.93 / 0.67 | 0.89 / 0.83 | 0.95 / 0.64 | 0.97 / 0.82 |

- **C1 (not worse than the better parent on every seed): not met.** Seed 7: B2TVD4 fails mid45 where B2TV passes. Seed 11: it passes up to mid42 while B2TD passes burst. Seed 23: it fails mid45 where B2TD passes.
- **C2 (strictly heavier than the better parent on at least 2 seeds): not met** (0 of 3).
- **C3 (seed 7 mid50 within 0.03 of B2TV): not met.** Doc 0.95 vs 1.00 (-0.05). It also lost doc attainment to the cap at lighter loads (seed 7 mid45: 0.86 vs 0.92 and 0.94 for the parents; seed 11 burst 0.86 vs 0.92).
- **C4 (in cells where the parents miss different classes, within 0.03 of the better parent per class): 3 of 4 met** (seed 7 mid42 and burst, seed 23 burst; seed 23 mid42 misses on doc, 0.82 vs 0.87). In those cells the combination takes engine priority's chat attainment (0.97 to 0.99) and demotion's document attainment (0.79 to 0.87) together. In none of them does the document attainment reach the 0.90 target, so no extra cell passes.

## What the data support

1. **The combination does not raise the SLO-constrained load level.** On no seed does it pass a heavier level than the better of its parents; at lighter loads the 4-document cap costs documents attainment (seed 7 mid50 0.95, mid45 0.86).
2. **It does combine the two benefits at overloaded cells** (C4: 3 of 4), but at those cells documents are below 0.90 anyway, so the benefit shows as a better chat/doc balance, not a pass. For example seed 7 mid42: B2TV 1.00 / 0.74, B2TD 0.90 / 0.86, B2TVD4 0.99 / 0.87.
3. **Where the document queue lives decides whether demotion can act.** Attempt 1's cap never bound, so documents queued in the engine's FCFS waiting queue and demotion had no effect; attempt 2 forces the document queue to the gateway. This is the same placement lesson as study 7, now on the demotion side: the rule must be applied at the first queue where the request waits.
4. **Replicate noise is larger than the margins several earlier conclusions rested on** (doc SLO mean 0.035, max 0.095 between two effective replicates of one configuration). Conclusions that depend on a single pass at 0.90 to 0.92 should be read as "within noise".

## Limitations

- Two repeats per cell; the 0.035 / 0.095 noise figures come from one pair of effective replicates over 10 cells and are not a variance model. Pooling replicates is a post hoc analysis.
- Attempt 2 tests one cap value (4) fixed by a rule; caps between 4 and 16 were not run, so whether an intermediate cap helps is unknown. The cost of the cap at lighter loads suggests the best cap depends on load.
- The doomed-document test uses estimates (150 ms hit, 72 ms per 1K tokens) measured on this host and ignores contention; no sensitivity was run.
- Engine priority with the LMCache connector was exercised only as shipped; no per-step instrumentation was done, so the mechanism sentence in point 3 is an interpretation of the queue-wait measurements, not a traced result.

## Reproduce (from `/workspace`)

```bash
export TRACE_PREFIX=s23 RUN_PREFIX=s23 REGISTRY=/workspace/results/s23_registry.csv
bash scripts/run_real_workload.sh "B2TVD4 mid45 r1" "B2TVD4 mid42 r1" "B2TVD4 burst r1" "B2TVD4 burst r2" "B2TVD4 mid42 r2" "B2TVD4 mid45 r2"   # attempt 2; attempt 1 used B2TVD
export TRACE_PREFIX=s11 RUN_PREFIX=s11 REGISTRY=/workspace/results/s11_registry.csv   # same six specs
export TRACE_PREFIX=real60 RUN_PREFIX=r60 REGISTRY=/workspace/results/real60_registry.csv
bash scripts/run_real_workload.sh "B2TVD4 mid50 r1" "B2TVD4 mid45 r1" "B2TVD4 mid42 r1" "B2TVD4 burst r1" "B2TVD4 burst r2" "B2TVD4 mid42 r2" "B2TVD4 mid45 r2" "B2TVD4 mid50 r2"
# offline: refresh the capacity files (see README section 12.4), then
PYTHONPATH=src python -m cacheflow.combo_summary --files 7=results/real/capacity_seed7.json 11=results/real/capacity_seed11.json 23=results/real/capacity_seed23.json --combo B2TVD4
```

Config letters: `VD` = engine priority for chat + gateway demotion for documents (16 documents in flight, did not bind), `VD4` = same with 4 documents in flight.
