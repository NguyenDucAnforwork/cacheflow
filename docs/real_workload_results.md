# Real-data mixed workload: chatbot + long-document QA on one RTX 3090

Status: executed on a new Vast.ai host (RTX 3090 24 GB, 31 GB RAM, 12 vCPU), 2026-11-22. All numbers below come from `results/real_registry.csv`, `results/real/analysis.json` and the per-run files `results/raw/real-*`. Existing results (`results/registry.csv`, `docs/main_results.md`) were not modified. DHAS was not revisited.

## Motivation

Earlier CacheFlow runs used synthetic documents. This study asks a more practical question: when short interactive chatbot requests share one inference server with long-document QA, how do (1) a CPU KV tier and (2) the prefill batching budget (`max_num_batched_tokens`) change latency, throughput and SLO attainment? It is an engineering measurement, not a reproduction of Strata, LMetric or QoServe.

## What is real and what is simulated

| Element | Real or simulated |
|---|---|
| Documents, questions, options, gold labels | **Real**: QuALITY v1.0.1 `htmlstripped.dev` (nyu-mll/quality) |
| Chatbot prompts | **Real**: first human turn of ShareGPT_V3 (`anon8231489123/ShareGPT_Vicuna_unfiltered`, revision `192ab2185289094fc556ec8ce5ce1e8e587154ca`), filtered (30–600 chars, <=3 newlines, ASCII, no code fence, small keyword blocklist, 8–120 tokens) and sampled with seed 7 |
| Request arrival times | **Simulated**: fixed-seed schedules (below). They are not taken from either dataset |
| Output budgets | Fixed: 48 tokens (doc), 96 tokens (chat); `temperature=0`; thinking disabled via the Qwen3 chat template |

Prompt text is not committed (`data/` is git-ignored). `results/real/real_{moderate,burst}.manifest.json` hold dataset hashes, article/question/conversation IDs, per-request prompt hashes, token statistics and arrival offsets.

## Setup

- Stack unchanged from `docs/reproduce.md`: vLLM 0.22.0, LMCache 0.5.3 (16 GiB CPU L1), Qwen3-1.7B BF16 revision `70d244cc`, GPU KV 6 GiB, `--max-num-seqs 16`, `--enforce-eager`, FIFO admission gateway. Prometheus metrics collector unchanged; OTLP profiling not used in these runs.
- Configurations: **B1** GPU prefix cache only; **B2** GPU + CPU tier; **B2T** same as B2 with `--max-num-batched-tokens 8192`.
- `max_num_batched_tokens`: on this GPU vLLM 0.22.0 defaults to **2048** for the OpenAI API server (`vllm/engine/arg_utils.py`, devices under 70 GiB). All earlier CacheFlow runs therefore used 2048. B1/B2 pass 2048 explicitly and B2T passes 8192, so the contrast is 2048 → 8192. Effective values were read from the live server (`/server_info`) and stored in each `*.summary.json`: `engine_max_num_batched_tokens` is 2048 or 8192, `engine_enable_chunked_prefill` is true, `engine_gpu_kv_tokens` is 56,160 (3,510 blocks × 16).
- Chunked prefill with LMCache: the only batched-token constraint in LMCache 0.5.3's MP connector applies to Mamba-hybrid models, not Qwen3. Both budgets restored 94,464 tokens from CPU in every B2/B2T run, so the combination works here.
- Run protocol: every run is a full cold restart (`scripts/set_mode.sh`), two identical tiny warm-up requests, then the replay. Order per trace: B1, B2, B2T, B2T, B2, B1 (two repeats per configuration, 12 runs).

### Traces (identical content, two arrival patterns)

- 14 distinct documents (token range 5,500–8,400, complete articles, no truncation), 3 real questions each: q0 first visit, q1 shortly after, q2 a late revisit after all documents were first seen (same document order, i.e. worst case for LRU). Plus 20 chat requests spread over the trace. 62 requests per trace.
- Moderate: first visits every 2.0 s, q1 +3.0 s, revisits every 1.5 s (span 52.5 s). Burst: first visits every 0.4 s, q1 +1.2 s, revisits every 0.3 s (span 11.8 s).
- Trace hashes: moderate `db3391e9…d626`, burst `f2df0859…586e` (full hashes in the manifests).

Token statistics (from the manifests; identical for both traces):

| Class | n | min | p50 | p95 | max |
|---|---|---|---|---|---|
| Doc prompts | 42 | 6,049 | 6,871 | 8,196 | 8,219 |
| Chat prompts | 20 | 21 | 30 | 77 | 116 |

Shared prefix between questions on the same document: p50 6,837 tokens (min 5,944, max 8,147, n=28). Working set: 98,130 unique document tokens versus 56,160 tokens of GPU KV, i.e. **1.75×** engine-reported capacity (CPU L1 holds 16 GiB ≈ 143K tokens, so the CPU tier holds it all). Output length: chat mean 94.05 tokens, doc 48 tokens (budget reached in every run).

### SLOs (fixed before the runs)

Chat TTFT ≤ 1 s, doc TTFT ≤ 3 s, TPOT ≤ 100 ms for both. TTFT is measured from the scheduled arrival. A failed request counts as an SLO failure. Goodput = requests meeting both targets ÷ (last completion − first scheduled arrival). TPOT is undefined for ≤1 output token and is then treated as met (never occurred here: all requests produced >1 token).

## Results

Means of two runs per cell (both runs given where they differ). Per-run numbers are in `results/real/analysis.json`.

### Burst trace (GPU saturated)

| | B1 | B2 | B2T |
|---|---|---|---|
| Chat TTFT p50 / p95 (s) | 1.60 / 3.11 | 0.61 / 2.54 | 0.57 / 1.95 |
| Doc TTFT p50 / p95 (s) | 1.83 / 3.59 | 0.88 / 2.87 | 0.55 / 2.31 |
| Chat SLO attainment (n=20) | 0.30–0.35 | 0.60 / 0.60 | 0.70 / 0.70 |
| Doc SLO attainment (n=42) | 0.86–0.88 | 0.95 / 0.95 | 1.00 / 1.00 |
| Goodput (req/s) | 2.54 | 4.00 | 4.31 |
| Run duration (s) | 16.9 | 13.0 | 13.0 |
| Output tokens/s | 231 | 300 | 300 |
| Prompt tokens: GPU hit / CPU restore / computed | 99.7K / 0 / 197.3K | 99.5K / 94.5K / 102.8K | 99.7K / 94.5K / 102.8K |
| Σ per-request prefill time (s) | 26.5 | 16.3 | 17.5 |
| Gateway admission wait, chat p50 / p95 (s) | 0.86–0.95 / 2.11–2.17 | 0.20 / 1.78–1.94 | 0.003 / 1.42–1.50 |
| Gateway admission wait, doc p50 / p95 (s) | 0.80–0.86 / 2.10–2.21 | 0.11–0.12 / 1.91–2.05 | 0.03 / 1.46–1.52 |
| vLLM mean waiting-queue time (s) | 0.25–0.36 | 0.17–0.24 | 0.05–0.06 |
| TPOT p95 chat / doc (ms) | 76 / 66 | 53–56 / 56–61 | 51 / 52–53 |

### Moderate trace

All three configurations met every SLO (attainment 1.00 for both classes, 62/62 requests, goodput 1.16 req/s, 73 output tokens/s; the run is arrival-limited). The visible differences:

| | B1 | B2 | B2T |
|---|---|---|---|
| Doc TTFT p50 (ms) | 435 | 166 | 168 |
| Doc TTFT p95 (ms) | 567 | 540 | 489 |
| Chat TTFT p95 (ms) | 414 / 222 | 430 / 431 | 121 / 396 |
| Σ per-request prefill time (s) | 13.3 | 8.1 | 7.7 |

### Answer quality and output differences

QuALITY accuracy (letter parsed from the generated text, n=42 per run): B1 0.57–0.62, B2 0.57–0.62, B2T 0.60–0.62. One question is 2.4 points, so these cannot separate the configurations. They only show the harness produces plausible answers (chance is 0.25). Generated text is stored locally in `results/raw/*.outputs.jsonl` (git-ignored).

`temperature=0` did not give identical text: against the first B1 run on the same trace, 14–27 of 62 outputs differ in text, **including the repeat of B1 itself** (17 on burst, 14 on moderate). The answer letter changed for 0–1 of 42 documents for B1 repeats and B2, but 3–5 of 42 for B2T (3 on moderate, 5 on burst, both repeats). A plausible cause is that a larger batch changes the bf16 kernel shapes; this was not isolated here. Semantic impact beyond the answer letter was not evaluated.

## Interpretation (what the measurements support)

1. **The CPU tier removes redundant prefill, which is what frees capacity under working-set pressure.** The documents total 1.75× GPU KV, so with LRU the late revisits miss the GPU. B1 recomputed 197.3K prompt tokens; B2 computed 102.8K and restored 94.5K tokens from LMCache (−48% computed prefill; identical in every B2/B2T run). Summed per-request prefill time fell from 26.5 s to 16.3 s (burst) and 13.3 s to 8.1 s (moderate). Under burst, the same work finished in 13.0 s instead of 16.9 s and doc SLO attainment rose from ~0.87 to 0.95, chat from ~0.33 to 0.60, goodput 2.54 → 4.00 req/s. Chat requests benefit indirectly: they never touch the cache, but they stop queueing behind recomputed document prefills.
2. **Under moderate load the tier only helps latency, not SLO attainment.** Doc p50 TTFT drops from 435 to 166 ms because revisits are restored instead of recomputed, but every request already met its SLO, so goodput is unchanged.
3. **Raising `max_num_batched_tokens` from 2048 to 8192 helped further under burst, in both repeats.** Chat p95 2.54 → 1.95 s (runs: 2.51/2.58 vs 1.95/1.95), doc p95 2.87 → 2.31 s, while the chat gateway-admission wait fell (p50 0.20 s → 0.003 s, p95 1.78–1.94 s → 1.42–1.50 s) and vLLM's mean waiting-queue time fell from 0.17–0.24 s to 0.05–0.06 s. Summed prefill time did not fall (16.3 s vs 17.5 s, ranges overlap), so the gain is in how quickly in-flight slots turn over and requests get scheduled, not in less prefill compute. A plausible explanation is that a 7K-token prompt needs about 4 scheduler steps at 2048 and about 1 at 8192, so slots free sooner and queued requests start earlier; per-step overhead was not measured, so that mechanism remains a hypothesis. The chat SLO attainment gain (0.60 → 0.70) is two requests out of twenty per run, replicated in both runs of this one trace.
4. **A large budget did not hurt chat TPOT** (p95 51 ms vs 53–56 ms). We did not measure decode stalls directly.
5. **Chat still misses its 1 s TTFT for 30% of burst requests with B2T (40% with B2).** Under burst most of the remaining delay is queueing before dispatch: the FIFO gateway admits at most 16 requests in flight, shared by both classes, and even with B2T the chat gateway wait has p95 1.42–1.50 s of a 1.95 s TTFT p95 (vLLM's own waiting queue averages only 0.05 s). Neither the CPU tier nor the budget gives chat priority over 7K-token document prefills. This identifies where the violations arise; a priority or per-class admission policy was not tested. Under the moderate trace the gateway wait is ~2 ms for chat and ~17 ms for doc requests.

## Limitations

- One host, one model, one trace seed (14 documents, 20 chat prompts); arrival patterns are simulated. Two repeats per cell are not independent trace samples.
- Small samples: 20 chat requests per run, so p95 is essentially the second-largest value, and one request changes attainment by 0.05. The moderate chat p95 varies across repeats (B2T 121 ms vs 396 ms), so moderate-trace chat p95 differences between configurations are not interpretable.
- Output throughput in this open-loop replay is total tokens ÷ run duration, and duration is bounded by the trace span plus drain time. The 231 → 300 tokens/s change reflects a shorter drain, not a higher peak decode rate.
- GPU utilization is sampled once per second via `nvidia-smi` and is noisy (moderate B2 repeat 1 reported 25% SM versus 51% in repeat 2), so it is not used as evidence.
- This host has 31 GB RAM versus 247 GB on the original host; B2 runs dropped to 8.5 GiB available RAM with a 16 GiB L1 budget. Results for the same KV/CPU budgets may differ on other hosts.
- Answer accuracy is a sanity check, not a result (n=42 per run).
- Nsight Systems exists on the host (`/usr/local/bin/nsys`) but was not used; no new profiling or OTLP data were collected, and nothing here infers PCIe bandwidth or GPU stalls.
- ShareGPT_Vicuna_unfiltered is unfiltered third-party chat data; only a keyword blocklist was applied.

## Failed attempts and corrections (kept for honesty)

- The first smoke run failed because syncing scripts from Windows converted them to CRLF (`set -o pipefail: invalid option name`); line endings were restored and no benchmark data were produced.
- A line-break bug in my first patch to `bench.py` caused a `SyntaxError` before any request was sent; fixed and re-run.
- `files.pythonhosted.org` throttled the vLLM install to tens of KB/s; the pinned versions were installed from the Aliyun PyPI mirror instead (same versions; wheels come from a third-party mirror).
- An earlier reproduction run (`repro-b1/b2-revisit-8k-r1`) on this host appended rows to `results/registry.csv` and `results/raw/gateway.jsonl`; they are append-only and were not used here.

## Reproduce (exact commands, run from `/workspace` on the host)

```bash
# 1. data and traces (downloads QuALITY zip and the 673 MB ShareGPT JSON; writes data/traces/*.jsonl and results/real/*.manifest.json)
PYTHONPATH=src /venv/main/bin/python -m cacheflow.real_workload --model-path /workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e
# 2. 12 runs in the order used here (each: cold restart, warm-up, replay; stops GPU services at the end)
bash scripts/run_real_workload.sh "B1 moderate r1" "B2 moderate r1" "B2T moderate r1" "B2T moderate r2" "B2 moderate r2" "B1 moderate r2" \
  "B1 burst r1" "B2 burst r1" "B2T burst r1" "B2T burst r2" "B2 burst r2" "B1 burst r2"
# 3. analysis, figures and results/real/analysis.json
PYTHONPATH=src /venv/main/bin/python -m cacheflow.real_analyze
```

Figures: `results/figures/real_workload/per_class_latency.png`, `goodput_throughput.png`, `kv_cache_accounting.png`.

Note: in this execution the first run (B1 moderate r1) was launched alone as a smoke test and the other eleven in a second batch, with the same script and no changes between them.
