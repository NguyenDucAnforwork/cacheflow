# Robustness of the capacity result, and why engine-level priority wins

Sixth follow-up. Pre-registered in [robustness_mechanism_prereg.md](robustness_mechanism_prereg.md); evaluated with `python -m cacheflow.robustness_summary`. Builds on [capacity_priority_results.md](capacity_priority_results.md). Same host (RTX 3090), stack, model, SLOs (chat TTFT <= 1 s, doc <= 3 s, TPOT <= 100 ms), B2, `max_num_batched_tokens` 8192; 60 new runs, 2 repeats per cell with reversed order on the second repeat. Data: `results/real60_registry.csv`, `results/s11_registry.csv`, `results/s23_registry.csv`, `results/real/capacity_seed{7,11,23}.json`, `results/real/robustness_summary.json`, raw `results/raw/s23-*`, `*mid42*`, `*b2tv24*`, `*b2tv32*`, `*b2tp24*`, `*b2tp32*`, figures `results/figures/capacity/`.

## Part 1: is the headline robust across document sets?

New: a third document set (seed 23) and a new load level `mid42` (first visits every 0.42 s, 8.2 req/s offered) on all three seeds. Chat / doc SLO attainment; `*` = pass (chat >= 0.95 and doc >= 0.90).

| Seed | Config | mid50 (6.9 req/s) | mid45 (7.6) | mid42 (8.2) | burst (8.6) | Heaviest pass on the common grid |
|---|---|---|---|---|---|---|
| 7 | gateway chat-first (B2TP) | 0.98 / 1.00 * | 0.94 / 0.83 | 0.93 / 0.75 | 0.94 / 0.69 | mid50 |
| 7 | chat-first + demotion (B2TD) | 0.96 / 0.99 * | 0.94 / 0.94 | 0.90 / 0.86 | 0.89 / 0.79 | mid50 |
| 7 | engine priority (B2TV) | 1.00 / 1.00 * | 0.99 / 0.92 * | 1.00 / 0.74 | 0.98 / 0.71 | **mid45** |
| 11 | B2TP | 1.00 / 1.00 * | 1.00 / 1.00 * | 0.93 / 0.96 | 0.99 / 0.83 | mid45 |
| 11 | B2TD | 1.00 / 1.00 * | 1.00 / 1.00 * | 0.97 / 0.95 * | 0.99 / 0.92 * | **burst** |
| 11 | B2TV | - | 1.00 / 1.00 * | 1.00 / 0.99 * | 0.98 / 0.81 | mid42 |
| 23 | B2TP | 0.97 / 1.00 * | 1.00 / 0.87 | 0.94 / 0.80 | 0.93 / 0.67 | mid50 |
| 23 | B2TD | - | 0.98 / 0.93 * | 0.94 / 0.87 | 0.89 / 0.83 | **mid45** |
| 23 | B2TV | 1.00 / 1.00 * | 0.99 / 0.89 | 0.93 / 0.76 | 0.95 / 0.64 | mid50 |

Seed 23 also: B1 2048 0.40 / 0.98 and B2 2048 0.58 / 1.00 at mid50 (both fail), B2 8192 FIFO 0.68 / 1.00 at mid50 and 0.55 / 1.00 at mid45 (fail). The B1 / B2 / FIFO brackets on seed 23 are "below tested range" because only the levels shown were run.

- **R1 (ordering B1 <= B2 <= B2 8192 FIFO <= B2TP <= B2TV on seed 23): met, weakly.** The three lower configurations fail the lightest level that was run and B2TP and B2TV both pass mid50, so no later configuration has a lighter bracket than an earlier one; the lower ones were not tested at lighter levels, so it is not a measured separation.
- **R2 (B2TV passes a heavier level than B2TP on at least 2 of 3 seeds): met, at the threshold.** Seed 7 (mid45 vs mid50) and seed 11 (mid42 vs mid45) yes; seed 23 no (both mid50; B2TV at mid45 misses the doc target by 0.01, 0.89). On seed 7 B2TV's mid45 pass has doc 0.92, also a narrow margin.
- **R3 (seed 11 B2TV passes mid45): met** (1.00 / 1.00).
- **R4 (first failures):** B2TP first fails at mid45 (seed 7), mid42 (seed 11), mid45 (seed 23); B2TD at mid45 (seed 7, chat 0.94), burst never on seed 11 within the tested range (passes burst), mid42 (seed 23); B2TV at mid42 (seed 7, doc 0.74), burst (seed 11, doc 0.81), mid45 (seed 23, doc 0.89).

**What this changes.** The claim "engine-level priority reaches a heavier level than gateway chat-first" holds on 2 of 3 document sets, with thin margins. The claim that engine priority is the *best* configuration does not: on seeds 11 and 23 chat-first + demotion passes a heavier level than engine priority (burst vs mid42; mid45 vs mid50), and on seed 7 engine priority is best. Which of the two wins depends on the document set, and they were never combined; the heaviest-pass ranking differs across seeds.

## Part 2: why does engine-level priority win? (seed 7, mid45 and burst)

Gateway width = in-flight cap at the gateway; vLLM `max_num_seqs` is 16. With width 16 the gateway holds the queue; with width > 16 the excess waits in vLLM's waiting queue. Engine priority (V) sends priority 0 / 1 and the gateway is FIFO; gateway chat-first (P) leaves the engine FCFS.

| Load | Width | Engine priority V | Gateway chat-first P | V minus P (chat, doc) | Pre-registered rule |
|---|---|---|---|---|---|
| mid45 | 16 | not run | 0.94 / 0.83 | - | - |
| mid45 | 24 | 0.94 / 0.90 | 0.58 / 0.96 | +0.36, -0.06 | inconclusive |
| mid45 | 32 | 0.99 / 0.87 | 0.57 / 1.00 | +0.43, -0.13 | inconclusive |
| mid45 | 64 | 0.99 / 0.92 * | 0.57 / 1.00 | (+0.42, -0.08) | (control from the previous study) |
| burst | 16 | not run | 0.94 / 0.69 | - | - |
| burst | 24 | 0.64 / 0.75 | 0.47 / 0.75 | +0.17, 0.00 | H-order |
| burst | 32 | 0.97 / 0.67 | 0.31 / 0.85 | +0.66, -0.18 | inconclusive |
| burst | 64 | 0.98 / 0.71 | 0.32 / 0.89 | (+0.66, -0.18) | (control) |

**Overall verdict by the pre-registered rule: mixed** (one cell H-order, three inconclusive). The rule compares at equal width, which turned out to be the wrong comparison: it classifies a trade-off (chat up by 0.17 to 0.66, doc down by 0 to 0.18) as inconclusive.

What the cells do show:

- **H-width is not supported.** Widening the gateway does not bring gateway chat-first closer to engine priority; it destroys it. At mid45 gateway chat-first falls from 0.94 chat at width 16 to 0.57 to 0.58 at widths 24, 32 and 64, which is FIFO-level (FIFO 0.57). Once the gateway admits more than the 16 sequences the engine runs, the excess queues in vLLM's FCFS waiting queue, and gateway ordering no longer applies there.
- **Engine priority keeps its effect across widths 24 to 64 at mid45** (chat 0.94, 0.99, 0.99), but at burst it needs the width: at width 24 chat is 0.64, at 32 and 64 it is 0.97 and 0.98. A plausible reading (not tested): beyond the width the gateway's FIFO queue holds chat behind documents, and engine priority only sorts what has already entered the engine.
- **Reading:** priority ordering takes effect in the *first queue where requests wait*. Gateway chat-first works when the gateway is that queue (width <= engine slots, no engine queue); engine priority works when the engine is that queue (width large enough that chat arrivals get in). Any FCFS queue upstream of the ordering point defeats it.
- **Not explained:** why engine priority at width 64 is still slightly better than gateway chat-first at width 16 (mid45: 0.99 / 0.92 vs 0.94 / 0.83). Preemption does not explain it (0 to 1 preemptions). Candidates, untested: per-step admission without the gateway's per-slot handoff latency; engine-side ordering of documents behind the chat requests.

## Limitations

- Three document sets, one host and model, 2 repeats per cell; request-level bootstrap intervals understate run-to-run variance. Several decisive cells are within 0.01 to 0.02 of a threshold (seed 7 B2TV mid45 doc 0.92; seed 23 B2TV mid45 doc 0.89).
- Seed 23 has no lighter-level cells for B1, B2 and FIFO, and the seed 11 B2TV mid50 and the width-16 engine-priority cells were not run.
- The width sweep is seed 7 only, at two loads; the pre-registered decision rule was a poor fit and is reported as it fired.
- Engine priority and demotion were not combined; the heaviest-pass ranking between them depends on the seed.

## Reproduce (from `/workspace`)

```bash
PYTHONPATH=src /venv/main/bin/python -m cacheflow.real_workload --model-path <snapshot> --prefix s23 --seed 23 --chats 60   # also adds mid42 to real60 and s11
bash scripts/run_real_workload.sh "B1 mid50 r1" ...          # see docs/robustness_mechanism_prereg.md for the cell list; configs: B2TV24, B2TV32, B2TP24, B2TP32 for the width sweep
PYTHONPATH=src python -m cacheflow.capacity_analyze --registry results/s23_registry.csv --run-prefix s23 --trace-prefix s23 \
  --gateway results/raw/gateway_*_runs.jsonl --out-json results/real/capacity_seed23.json --figure results/figures/capacity/capacity_seed23.png   # likewise seeds 7 and 11
PYTHONPATH=src python -m cacheflow.robustness_summary --files 7=results/real/capacity_seed7.json 11=results/real/capacity_seed11.json 23=results/real/capacity_seed23.json
```
