# Why does engine priority have the largest run-to-run spread, and demotion the smallest?

Offline investigation (no new runs) on the 12 decisive cells of [hardening_results.md](hardening_results.md): seeds 7 / 23 / 11 at mid45 / mid45 / mid42 and burst, three configurations (gateway chat-first B2TP, chat-first + demotion B2TD, engine priority B2TV), 6 runs per cell, 42 document requests per run. Code: `python -m cacheflow.variance_investigate` (output `results/real/variance_investigation.json`, figure `results/figures/hardening/variance_mechanism.png`). Written after the first results of the study; the cap-sweep experiment that tests the explanation is pre-registered in [ladder_capsweep_prereg.md](ladder_capsweep_prereg.md) and its outcome is in [ladder_capsweep_results.md](ladder_capsweep_results.md).

## The question

Run-to-run SD of doc SLO attainment (mean over the 4 cells): B2TD 0.014, B2TP 0.025, B2TV 0.033. A configuration with a larger spread needs more repeats to be ranked reliably and its pass/fail at a 0.90 threshold flips more often. Is that because the engine-priority runs are noisier per request, or because of something about how the outcomes move together?

## Candidate explanations and what each predicts

| Explanation | Prediction |
|---|---|
| E1: more requests sit at the edge, so there are more *unstable* requests (pass rate strictly between 0 and 1) | spread rises with the unstable count |
| E2: individual requests have noisier timings | larger per-request cross-run SD of TTFT |
| E3: outcomes of different requests are *positively correlated* within a run (a run-wide shift moves many near-threshold requests together) | observed SD larger than the SD predicted from independent per-request flips; a large "design effect" |
| E4: more of the TTFT mass is *near the SLO threshold* (3 s), so a small shift flips more requests | spread correlates with the share of documents with TTFT within 0.5 s of 3 s |

Per-request outcomes were taken as a requests x runs matrix. "Independent-flip SD" is sqrt(sum p_i (1 - p_i)) / n with p_i the request's pass rate over the runs; the "design effect" is the variance of the per-run mean outcome divided by what independent requests would give, so it is 1 for independent requests, above 1 for positive correlation and below 1 for negative correlation (compensating flips).

## Results (mean over the four decisive cells)

| Config | Observed SD | Independent-flip SD | Unstable requests | Median per-request TTFT SD | Docs within 0.5 s of the SLO | Outcome design effect |
|---|---|---|---|---|---|---|
| gateway chat-first | 0.025 | 0.020 | 3.8 | 52 ms | 0.17 | 1.26 |
| chat-first + demotion | 0.014 | 0.024 | 6.0 | 76 ms | 0.10 | **0.30** |
| engine priority | **0.033** | 0.022 | 4.5 | **33 ms** | **0.20** | **1.94** |

Across the 12 (cell, configuration) points the observed SD correlates **-0.08** with the unstable-request count (E1), 0.12 with the independent-flip prediction, and **0.66** with the share of documents near the SLO (E4).

- **E1 is not supported.** Engine priority does not have more unstable requests; demotion has more (6.0 vs 4.5).
- **E2 is not supported.** Engine priority has the smallest per-request timing noise (33 ms); demotion the largest (76 ms, with the largest values at burst).
- **E3 is supported.** The independent-flip model predicts about the same SD for all three (0.020 to 0.024), but engine priority's observed SD is 1.5x higher than that and demotion's is 0.6x: the outcomes of engine priority's documents move **together** (design effect 1.94), demotion's move **against** each other (0.30, compensating flips: when one document misses, another that was going to miss now passes, or the reverse), and chat-first sits in between (1.26).
- **E4 is partly supported.** Engine priority has the most documents near the threshold (0.20) and demotion the fewest (0.10); the correlation is moderate (0.66 over 12 points) and the effect is confounded with E3.

## Interpretation (a hypothesis, not a traced result)

With first-come-first-served queueing for documents (engine priority leaves documents FCFS inside vLLM), the delay of each document depends on the work queued ahead of it; a run in which the queue is slightly longer shifts the TTFT of many consecutive documents by similar amounts, and the documents that are already close to 3 s all flip in the same direction. Lag-1 autocorrelation of the TTFT residuals along the arrival order is positive for all three (+0.12 to +0.13) so autocorrelation alone does not separate them; the difference is in the outcome design effect and in how much mass is near the threshold. Demotion decides at admission time which documents are served now and which are pushed to the back, so a shift in load lands on documents that were going to miss anyway (its share of far-miss documents is 0.07 vs 0.01 for engine priority), and the savable ones are insulated: that produces the compensating, negatively correlated flips.

This is consistent with the "first queue where requests wait" lesson from study 7: where the queue for documents lives determines both which class gets served and how correlated the outcomes are.

## What would test it

If queueing in the engine's FCFS waiting queue causes the common-mode correlation, then moving that queueing to the gateway where demotion acts should reduce the design effect in a dose-response manner as the cap on documents in flight is lowered. That is the cap sweep (caps 4, 8, 12 against no cap) pre-registered as M1 to M4 in [ladder_capsweep_prereg.md](ladder_capsweep_prereg.md); results in [ladder_capsweep_results.md](ladder_capsweep_results.md).

## Outcome of the tests (added after studies 10 and 11)

The cap sweep ([ladder_capsweep_results.md](ladder_capsweep_results.md)) failed its dose-response prediction; the 3-way decomposition ([locus_results.md](locus_results.md)) then separated the factors: **queue location and a cap of 4, 8 or 12 documents in flight, with FIFO order, do not remove the positive correlation (design effect 1.65, 1.65, 1.43 vs 1.94 for engine priority); adding the demotion order does (0.77 at cap 4, 0.30 without a cap)**. So the best-supported reading is that the *ordering policy* decorrelates the outcomes (the "compensating flips" of the table above), not the location of the queue. Concurrency inside the engine's own queue could not be varied (vLLM `max_num_seqs` 4 and 8 collapse the server); the concurrency contrast was obtained under FIFO with a gateway cap. The conclusion is post hoc and rests on the valid contrasts.

**Update (direct trace, [locus_results.md](locus_results.md)):** the gateway's `demoted` flag shows that under demotion every miss is a flagged document (66 of 66) and none of the 942 unflagged documents missed, so the mechanism is *insulation of the savable documents plus a bounded set of misses* rather than flips that compensate each other.

**Update (study 12, [engine_demote_results.md](engine_demote_results.md)):** the last missing corner was filled by a small patch to vLLM's waiting queue; adding the demotion order *inside the engine queue* also lowers the variance inflation (1.94 to 0.59) and raises the number of decisive cells passed from 2 of 4 to 4 of 4. The ordering, not the queue location, is the factor in both queues.

## Limitations

- 12 points from 4 cells and 3 configurations; the correlations are descriptive and the cells share seeds and loads.
- The design effect is estimated from 6 runs per cell; per-cell values range widely (for example 0.1 to 3.1 for the outcome), so only the average over cells is interpreted.
- Documents are 42 per run and 14 distinct documents; visit types (first visit, GPU hit, late revisit) contribute differently; most unstable requests are GPU-hit second visits (q1), some first visits, none of the CPU-restored revisits (q2).
- The explanation is about correlation structure; it does not identify the specific vLLM mechanism, which would need per-step scheduler traces.
