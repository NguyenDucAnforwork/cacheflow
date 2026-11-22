# Prefill budget, load and queue order: where does short-request TTFT go?

Follow-up to [real_workload_results.md](real_workload_results.md). Same host (RTX 3090), stack and model; 20 runs executed 2026-11-22 17:53–18:17 host time (24 minutes of runs). Data: `results/real60_registry.csv`, `results/real/chunk_analysis.json`, raw per-run files `results/raw/r60-*`, figures in `results/figures/chunk_study/`.

## Why this study

The first study left three open items: the larger prefill budget (`max_num_batched_tokens` 2048 → 8192) helped under burst without a measured cause; chat still missed its SLO under burst; and 20 chat requests per run made p95 noisy. Related work frames the budget as a trade-off: finer chunks cost overhead while coarser chunks cause head-of-line blocking ([FlowPrefill](https://arxiv.org/html/2602.16603v1)); QoServe and SLOWEAVE pick chunk sizes dynamically from deadline slack ([QoServe](https://www.microsoft.com/en-us/research/wp-content/uploads/2025/10/QoServe_CC_final_v2.pdf), [SLOWEAVE](https://arxiv.org/pdf/2609.07883)). I read abstracts only, not the full papers; this study does not implement their schedulers.

**Research question.** Under a mixed chat + long-document load with the CPU KV tier on, is short-request TTFT bound by queueing or by prefill-step granularity, and does the answer change with load?

Hypotheses written before the runs: **H1** under burst, 8192 cuts chat p95 TTFT by at least 20% versus 2048, through gateway wait; **H2** under light load the sign flips (a large step delays arriving chat); **H3** larger budgets lengthen inter-token gaps of decoding requests; **H4** admitting chat first brings chat SLO attainment to at least 0.90 while doc stays at least 0.95.

## Setup

- Same 14 real QuALITY documents and questions as before; chat prompts raised to **60** real ShareGPT first turns (102 requests per trace). Arrival times remain **simulated** fixed schedules: moderate (first visits every 2.0 s, span 52.5 s), medium (0.9 s, span 25.3 s), burst (0.4 s, span 11.8 s). Medium is new. Trace hashes: moderate `452744…`, medium `87b8c3…`, burst `3afbb1…` (full values in `results/real/real60_*.manifest.json`). Output budgets 48 (doc) and 96 (chat).
- Configurations (all with explicit `--max-num-batched-tokens`, effective value read from `/server_info` and stored per run): B2 2048, B2 8192, B2 8192 with **chat-first gateway admission** (chat admitted before queued doc requests, FIFO within class; one added policy, `class_first`), B2 4096, B1 2048, B1 8192. Full cold restart before every run.
- Runs: load × {2048, 8192} × 2 repeats in ABBA order for B2 (12 runs); chat-first ×2, B2 4096 ×2, B1 2048/8192 ×2 each under burst only (8 runs). Two repeats per cell; 120 chat requests and 84 doc requests per cell.
- Per request, TTFT (from scheduled arrival) is split into gateway admission wait (`queue_wait_ms`), engine segment (gateway dispatch to first token) and a small remainder. Also recorded: maximum inter-token gap per request, doc service time by visit type (q0 first visit computed, q1 GPU hit, q2 late revisit restored from CPU), SLO attainment (chat TTFT ≤ 1 s, doc ≤ 3 s, TPOT ≤ 100 ms). Confidence intervals are bootstrap resamples over request IDs, with config pairs resampled jointly; they do not include run-to-run variance (only two repeats).
- `vllm:iteration_tokens_total` was added to the sampler but gave the same step count for 2048 and 8192 (556 vs 554 in a first check), so it does not measure scheduler steps and was not used. `vllm:num_preemptions_total` was 0 in all runs.

## Results

### Prefill budget by load (B2, chat TTFT p95 and paired difference 8192 − 2048)

| Load | Chat p95 2048 → 8192 (ms) | Paired diff, 95% CI (ms) | Doc p95 2048 → 8192 (ms) | Chat max inter-token gap p95 (ms) | Doc q0 engine time (ms) | Doc q2 (restored) engine time (ms) |
|---|---|---|---|---|---|---|
| Moderate | 340 → 319 | −20 [−38, −4] | 547 → 497 | 158 → 464 | 475 → 427 | 144 → 142 |
| Medium | 432 → 364 | −68 [−81, −30] | 587 → 499 | 231 → 471 | 503 → 433 | 144 → 143 |
| Burst | 3,429 → 3,023 | −406 [−488, −307] | 3,697 → 3,305 | 165 → 491 | 616 → 505 | 176 → 188 |

All SLOs were met in every moderate and medium run (attainment 1.00 for both classes). Chat TPOT p95 was unchanged (18 ms at moderate for both budgets).

### Burst trace: all configurations (two runs each)

| Config | Chat TTFT p95 (s) | Chat SLO | Doc TTFT p95 (s) | Doc SLO | Goodput (req/s) | Run duration (s) | Gateway wait, chat mean / p95 (s) |
|---|---|---|---|---|---|---|---|
| B1 2048 | 5.23 | 0.17 | 5.74 | 0.54 | 1.70 | 19.1 | 2.43 / 4.75 |
| B1 8192 | 4.41 | 0.18 | 4.77 | 0.64 | 2.08 | 18.3 | 1.99 / 4.25 |
| B2 2048 | 3.43 | 0.19 | 3.70 | 0.81 | 3.27 | 13.9 | 1.75 / 3.22 |
| B2 4096 | 3.28 | 0.23 | 3.54 | 0.83 | 3.52 | 13.8 | 1.64 / 3.08 |
| B2 8192 | 3.02 | 0.30 | 3.31 | 0.88 | 4.06 | 13.6 | 1.42 / 2.84 |
| B2 8192 chat-first | **0.97** | **0.94** | 4.61 | 0.69 | 6.44 | 13.3 | 0.38 / 0.93 |

Per-run chat p95 for B2 8192: 3.04 and 2.97 s; for B2 2048: 3.39 and 3.46 s. Paired p95 differences (CI): chat-first minus B2 8192 chat −2,049 ms [−2,197, −1,662], doc +1,308 ms [+1,210, +1,820]; B1 8192 minus B1 2048 chat −813 ms [−865, −405]; B2 4096 minus B2 2048 chat −147 ms [−212, −84].

### Hypothesis outcomes

- **H1: partly supported.** Chat p95 fell 11.8% under burst, below the 20% threshold. The reduction is in gateway wait (mean 1.75 → 1.42 s) while the engine segment grew (mean 175 → 222 ms). The direction and location are as predicted, the size is not.
- **H2: not supported.** No sign flip. 8192 was better than 2048 at every load, with small gains at light load (chat p95 −20 ms and −68 ms, CIs exclude zero but exclude only small effects).
- **H3: supported.** The p95 of each chat request's longest inter-token gap rose 2–3× (158 → 464 ms, 231 → 471 ms, 165 → 491 ms), while TPOT p95 did not change. The ≤100 ms TPOT SLO is an average rate and does not see these roughly 0.5 s stalls.
- **H4: half supported.** Chat attainment rose to 0.94, but doc attainment fell to 0.69, below the 0.95 target.

## Interpretation (what the measurements support)

1. **Under burst the chat TTFT is mostly queueing before dispatch.** Gateway wait is ~1.4–1.7 s of a ~1.6–1.9 s mean TTFT for B2; the engine segment is 0.17–0.22 s. The FIFO gateway holds back chat behind document requests that occupy the 16 in-flight slots. This is the dominant term, not step granularity.
2. **A larger budget shortens prefill service time, and that is what shortens the queue.** In the no-queue regimes (moderate and medium, gateway wait ~2 ms) the engine time of a first-visit 7K-token document fell 10–14% (475 → 427 ms, 503 → 433 ms), while the late-revisit requests, whose KV is restored from CPU and need almost no prefill, did not change (144 → 142 ms, 144 → 143 ms). That contrast points at prefill compute service time (fewer steps for the same tokens) and not at the restore path. Per-step overhead was not measured, so "overhead per step under `--enforce-eager`" is a consistent explanation rather than a demonstrated one. Slots free sooner, so queued requests start sooner: B1 benefited by a similar relative amount (−16% chat p95) as B2 (−12%), i.e. the budget effect and the CPU tier effect (B1 → B2: −34% at 2048, −32% at 8192) look roughly independent.
3. **The cost of the larger budget is in the decode tail, not TTFT.** A step of up to 8192 tokens stalls every co-scheduled decode for ~0.5 s, which doubled to tripled the worst inter-token gap. This matches the head-of-line concern raised in the literature, but on this setup the TTFT benefit outweighed it, and the stated SLO would not detect it. A product SLO that includes a stall bound would change which budget is acceptable. I did not test that.
4. **Chat-first admission moves the SLO miss rather than removing it, because the burst saturates the GPU.** Chat p95 drops to 0.97 s and chat SLO to 0.94, but doc p95 rises from 3.3 to 4.6 s and doc SLO falls from 0.88 to 0.69. Under saturation there is no deadline slack for doc requests to give up (their p95 already exceeds 3 s at B2 8192), so priority only reallocates misses. Goodput in req/s rises 4.06 → 6.44, but it counts requests and chat requests are cheap (30-token prompts), so it overstates the benefit; decide by the per-class attainment. The slack idea in QoServe/SLOWEAVE would apply below saturation, which this study did not test with a slack-aware policy.
5. **Light and medium loads do not distinguish the budgets in SLO terms.** Everything met its SLO; chat p95 (~0.3–0.4 s) is set by arriving while a document step is running (median is ~40 ms).

## Limitations

- One host, one model (1.7B, `--enforce-eager`), one document set and seed; arrival times simulated; chat prompts from unfiltered ShareGPT with a keyword blocklist.
- Two repeats per cell. The repeat spread is small (e.g., 3.04 vs 2.97 s) but request-level bootstrap intervals understate run-to-run variance. Burst has a 12-second window, so the 60 chat requests are not independent.
- Prompts are at most 8,219 tokens, so 8192 is effectively unchunked for almost all documents; the comparison is chunked versus essentially unchunked. 4096 was only run under burst.
- The medium load is an interpolated setting chosen by me before running (0.9 s first-visit spacing), not derived from a measured capacity.
- Chat-first is a gateway-only policy keyed on a declared class header. vLLM's own `--scheduling-policy priority` (present in 0.22.0) and preemption interaction with the KV connector were not tested. The 16-slot in-flight cap is unchanged, so chat still waits 0.93 s at p95 when all slots hold documents.
- The `other` remainder (client/relay time) is small but not reported per cell. No Nsight or per-step instrumentation was done, so the step-overhead mechanism is unproven.
- Absolute burst numbers are not comparable with the 20-chat study (a heavier trace).

## Reproduce (from `/workspace` on the host)

```bash
PYTHONPATH=src /venv/main/bin/python -m cacheflow.real_workload --model-path <Qwen3-1.7B snapshot> --prefix real60 --chats 60
export TRACE_PREFIX=real60 RUN_PREFIX=r60 REGISTRY=/workspace/results/real60_registry.csv
bash scripts/run_real_workload.sh "B2 burst r1" "B2T burst r1" "B2T burst r2" "B2 burst r2" "B2TP burst r1" "B2TP burst r2" \
  "B2 medium r1" "B2T medium r1" "B2T medium r2" "B2 medium r2" "B2 moderate r1" "B2T moderate r1" "B2T moderate r2" "B2 moderate r2"
bash scripts/run_real_workload.sh "B2M burst r1" "B1 burst r1" "B1T burst r1" "B1T burst r2" "B1 burst r2" "B2M burst r2"
PYTHONPATH=src /venv/main/bin/python -m cacheflow.chunk_analyze
```

Config letters: `T` = 8192, `M` = 4096, none = 2048; `P` = chat-first gateway policy.

## Corrections made during the study

My first reading of `vllm:iteration_tokens_total` as a step counter was wrong (see Setup). A first plotting bug in the decomposition figure and the legend labels were fixed before the numbers above were produced.
