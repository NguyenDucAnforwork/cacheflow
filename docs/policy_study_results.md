# Queue order below saturation, and what a prefill step costs

Second follow-up to [real_workload_results.md](real_workload_results.md) and [chunk_study_results.md](chunk_study_results.md). Same host (RTX 3090), stack, model, 14 real QuALITY documents and 60 real ShareGPT chat prompts; 14 new serving runs plus one isolated probe (5 server restarts), executed 2026-11-22/23 host time. Hypotheses were written before the runs: [policy_study_prereg.md](policy_study_prereg.md). Data: `results/real60_registry.csv`, `results/real/policy_analysis.json`, `results/real/probe_analysis.json`, raw `results/raw/r60-mid*`, `r60-burst-b2ta*`, `probe-mnbt*`, figures in `results/figures/policy_study/`.

## Why

The previous study found that admitting chat first moved SLO misses from chat to doc under a burst, because the GPU was saturated and docs had no slack to give. That left two open items: (1) is there a load range, below saturation, where chat-first is free, and does an age cap on docs help; (2) the claim that the larger prefill budget helps through fewer scheduler steps was only consistent with the data, not measured.

**Research question.** Between "medium" (first document visits every 0.9 s) and "burst" (0.4 s), does chat-first admission still trade doc SLO for chat SLO, and does an age cap help?

## Setup

- Two new arrival profiles: `mid65` (first visits every 0.65 s) and `mid50` (0.5 s), same documents, questions and chat prompts as before (hashes of the earlier traces reproduce). Arrival times are simulated; content is real.
- B2 (GPU + CPU KV tier), `max_num_batched_tokens` 8192, 16 in-flight slots. Policies: FIFO; chat-first (`class_first`); chat-first with an age cap (`class_aged`): a request that has waited at least 1,500 ms since its scheduled arrival is treated like chat (FIFO among equals). The 1,500 ms was fixed before the runs and not tuned.
- Cells: `mid65` and `mid50` x 3 policies, 2 repeats each, reversed order on the second repeat; burst gets the new `class_aged` cell (2 runs) next to the earlier FIFO and chat-first cells; medium is the earlier FIFO cell (chat-first and age cap not run there). Per cell: 120 chat and 84 doc requests. Full cold restart before every run.
- SLOs as before: chat TTFT <= 1 s, doc TTFT <= 3 s, TPOT <= 100 ms. Confidence intervals: paired bootstrap over request IDs (they ignore run-to-run variance; two repeats).
- Probe: one real document per request, sequential, no queue, `max_tokens=1`, a unique prefix nonce so the prefix cache cannot hit, B1 (no CPU tier), `max_num_batched_tokens` 2048/4096/8192 (2048 and 8192 each restarted twice), 14 documents x 3 passes per restart (210 samples).

## Results

### Per-class SLO attainment and p95 TTFT (s), two runs per cell

| Load (first-visit spacing) | Policy | Chat p95 | Chat SLO | Doc p95 | Doc SLO | Goodput (req/s) | Docs admitted by age cap (per run) |
|---|---|---|---|---|---|---|---|
| medium (0.9 s) | FIFO | 0.36 | 1.00 | 0.50 | 1.00 | 3.88 | - |
| mid65 (0.65 s) | FIFO | 0.54 | 1.00 | 0.55 | 1.00 | 5.19 | - |
| mid65 | chat-first | 0.42 | 1.00 | 0.60 | 1.00 | 5.19 | - |
| mid65 | chat-first + age cap | 0.43 | 1.00 | 0.60 | 1.00 | 5.18 | 0, 0 |
| mid50 (0.5 s) | FIFO | 1.85 | 0.68 | 1.92 | 1.00 | 5.20 | - |
| mid50 | chat-first | **0.85** | **0.98** | 2.58 | **1.00** | 6.33 | - |
| mid50 | chat-first + age cap | 1.75 | 0.84 | 2.15 | 1.00 | 5.79 | 10, 10 |
| burst (0.4 s) | FIFO | 3.02 | 0.30 | 3.31 | 0.88 | 4.06 | - |
| burst | chat-first | 0.97 | 0.94 | 4.61 | 0.69 | 6.44 | - |
| burst | chat-first + age cap | 3.07 | 0.53 | 3.32 | 0.85 | 5.00 | 22, 25 |

(The medium cell and the burst FIFO / chat-first cells come from the previous study.) Selected paired differences with 95% CI (second policy minus first):

- mid50, FIFO to chat-first: chat SLO +0.30 [+0.18, +0.42]; chat p95 -1,265 to -646 ms; doc SLO unchanged at 1.00, doc p95 +576 to +773 ms.
- mid50, chat-first to age cap: chat SLO -0.14 [-0.23, -0.07], doc SLO unchanged.
- burst, chat-first to age cap: chat SLO -0.42 [-0.53, -0.30], doc SLO +0.15 [+0.07, +0.25].
- mid65: no SLO difference between any policies (all 1.00).

### Isolated prefill probe (no queue, no prefix hit)

| max_num_batched_tokens | Median TTFT (ms) | Mean scheduler steps per prompt | Median of per-restart medians |
|---|---|---|---|
| 2048 | 453 | 4.0 | 451, 457 |
| 4096 | 435 | 2.1 | 435 |
| 8192 | 415 | 1.1 | 415, 415 |

A least-squares fit of TTFT on token count and the expected step count (ceil of prompt tokens / budget) gives about **12 ms per extra step** (95% CI 10.9 to 13.2, bootstrap over documents) and about 72 ms per 1,000 prompt tokens. Every one of the 14 documents is 22 to 49 ms faster at 8192 than at 2048 (figure `prefill_probe.png`). The gain is roughly constant across prompt lengths, as a fixed per-step cost would predict.

## Hypotheses against outcomes

- **H-a (mid65: chat-first gives chat >= 0.95 with doc >= 0.90): met, but empty.** FIFO already meets every SLO at this load, so there is nothing to fix; chat-first only trims chat p95 (0.54 to 0.42 s, CI [-239, +4] ms, not clearly different).
- **H-b (mid50: chat-first pushes doc below 0.90, the age cap repairs it): not supported.** The premise failed: chat-first lifted chat from 0.68 to 0.98 while doc stayed at 1.00 (doc p95 2.58 s, still under 3 s). The age cap was not needed and it hurt, because 1.5 s is earlier than the docs' slack required: it admitted 10 docs per run ahead of chat and chat attainment fell to 0.84 with no doc gain in SLO terms.
- **H-c (some load where no policy keeps both classes on target): supported at burst only.** At burst: FIFO 0.30 / 0.88, chat-first 0.94 / 0.69, age cap 0.53 / 0.85 (chat / doc); none reaches chat >= 0.95 and doc >= 0.90. At mid50 chat-first reaches both.

## What the data support

1. **Chat-first is free while docs have slack, and the slack runs out between 0.5 s and 0.4 s spacing.** At mid50 the throughput is identical across FIFO and chat-first (duration 16.0 s in both) and doc p95 rises to 2.58 s but stays under its 3 s SLO; goodput in requests per second rises 5.20 to 6.33 only because more chat requests meet their SLO. Reordering helps exactly when total work fits and one class has deadline margin.
2. **At burst, ordering only redistributes misses; the age cap interpolates between FIFO and chat-first** (chat 0.30, 0.53, 0.94; doc 0.88, 0.85, 0.69). No policy tested attains both targets, so the load needs more capacity (or admission control), not a different order.
3. **The age cap as specified (1.5 s) was too eager.** Docs have a 3 s SLO and about 0.5 s of service time, so a cap near 2 to 2.3 s would have left chat-first intact at mid50. I did not run that value because I fixed 1.5 s beforehand and did not want to tune on the results; a slack-based cap (promote when remaining slack falls below the expected service time) is the natural next policy and is untested.
4. **The step-overhead explanation for the budget effect now has direct evidence.** With no queue, going from 2048 to 8192 shortens a 6 to 8K-token prefill by 22 to 49 ms (about 12 ms per step removed). The first-visit document engine times under load fell by 48 to 111 ms in the previous study, so the isolated cost accounts for the light-load part (48 ms observed at moderate load) but not all of the larger gains at medium and burst (70 and 111 ms); the remainder is unexplained here (for example decode-step interference) and was not measured.

## Limitations

- One host, one 1.7B model with `--enforce-eager`, one document set and seed; arrival times simulated. Two repeats per cell; bootstrap intervals over request IDs understate run-to-run variance, and 60 chat requests in a 12 to 20 second window are not independent.
- Chat-first keys on a client-declared class header at the gateway. vLLM's own priority scheduler and its interaction with the KV connector were not tested.
- Medium has only a FIFO cell. The load grid has four points, so "between 0.5 s and 0.4 s" is a bracket, not a measured threshold.
- The probe uses B1 (no CPU tier) and sequential requests; the step-cost fit assumes linearity (the 4096 to 8192 change, about 20 ms per step, is larger than 2048 to 4096, about 9 ms per step). It does not isolate co-scheduled decode effects.
- The age cap was evaluated at one fixed value.

## Reproduce (from `/workspace` on the host)

```bash
export TRACE_PREFIX=real60 RUN_PREFIX=r60 REGISTRY=/workspace/results/real60_registry.csv
PYTHONPATH=src /venv/main/bin/python -m cacheflow.real_workload --model-path <Qwen3-1.7B snapshot> --prefix real60 --chats 60   # adds mid65, mid50
bash scripts/run_real_workload.sh "B2T mid65 r1" "B2TP mid65 r1" "B2TA mid65 r1" "B2TA mid65 r2" "B2TP mid65 r2" "B2T mid65 r2" \
  "B2T mid50 r1" "B2TP mid50 r1" "B2TA mid50 r1" "B2TA mid50 r2" "B2TP mid50 r2" "B2T mid50 r2" "B2TA burst r1" "B2TA burst r2"
bash scripts/run_prefill_probe.sh 2048 8192 4096 8192 2048
PYTHONPATH=src python -m cacheflow.policy_analyze      # needs results/raw/gateway_policy_runs.jsonl (gateway lines of these runs)
PYTHONPATH=src python -m cacheflow.probe_analyze
```

Config letters: `T` = 8192, `P` = chat-first, `A` = chat-first with age cap (`AGE_CAP_MS`, default 1500).
