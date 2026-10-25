# V2 LoCoMo data and context fit audit

Audit date: 2026-10-25. Raw source is the official [LoCoMo repository](https://github.com/snap-research/locomo), commit `3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`; `data/locomo10.json` SHA256 is `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`. The file is kept outside Git under ignored `data/raw/` because the source license is CC BY-NC 4.0.

The tokenizer is `Qwen/Qwen3-1.7B` at revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`. Prompt version `locomo-text-v1` preserves speaker names, session dates/order, dialog IDs and text. It appends released `blip_caption` text where present; image URLs are never fetched. Gold answers, evidence labels and future sessions never enter the prompt. This is a **text-only adaptation**, not a multimodal LoCoMo score.

## Full-context P-QA fit

Each question uses the entire fixed conversation followed by its original question. All requests reserve 64 output tokens. The report at `results/v2/fit_report.json` records exact per-question tokenizer counts.

| Measure | Result |
| --- | ---: |
| Conversations / QA | 10 / 1,986 |
| QA input tokens p50 / p90 / max | 26,823 / 29,374 / 29,390 |
| Fit at 12,288 total tokens | 0 / 1,986 |
| Fit at 32,768 total tokens | 1,986 / 1,986 |
| Exact shared tokenized context prefix | 1,986 / 1,986 |
| QA with malformed or unknown evidence for checkpoint replay | 9 / 1,986 |

The model config advertises `max_position_embeddings=40960`, so 32,768 is within the model context setting. A BF16 KV estimate from the model config is `28 layers × 2 (K,V) × 8 KV heads × 128 head dimension × 2 bytes = 114,688 bytes/token`, or **3.5 GiB for one 32,768-token sequence** before block allocation and engine overhead. This is a planning estimate, not a measured vLLM allocation. A 4 GiB GPU KV budget is therefore a marginal full-context arm; E2 cannot begin until a memory pilot verifies it. The 8 GiB arm may allow more simultaneous full contexts, subject to model weight and runtime headroom on 24 GiB VRAM.

No full-LoCoMo accuracy score is claimed yet. The 30-request dev smoke trace uses only `conv-26` and `conv-30` (15 QA each); label any score from it a **LoCoMo pilot subset**. A full-context evaluation with all QA may be possible by length, but only if the server can run the chosen concurrency without OOM or unacceptable queuing.

## Split and trace integrity

The frozen conversation-level split is in `configs/v2_experiments.yaml`: six dev conversations (`conv-26`, `conv-30`, `conv-41`, `conv-42`, `conv-43`, `conv-44`), two validation (`conv-47`, `conv-48`), and two holdout (`conv-49`, `conv-50`). QA from the same conversation never crosses splits. The split is deterministic and exploratory; ten conversations do not support population-level significance claims.

Two ignored 30-request smoke traces were generated from the dev samples:

| Protocol | Arrival model | Requests | Trace SHA256 |
| --- | --- | ---: | --- |
| P-QA | seeded open-loop, interleaved, 2 QPS | 30 | `5acdf79bcaf5bf9a307f732d2ffb97256d41b13c210ef761be5986e44189bd9a` |
| P-SESSION | seeded open-loop, interleaved, 2 QPS, 1,000 ms session gap | 30 | `fdeb1efd65c992c2fc33f7b7b583e067ca359f85d9858f802db48752d1038209` |

P-SESSION only exposes history through the last session containing all cited evidence and orders checkpoints chronologically. Invalid source evidence is preserved for audit and excluded from checkpoint replay. The arrival schedule is constructed, not a production trace.

## AgentPerfBench boundary

The public [AgentPerfBench dataset card](https://huggingface.co/datasets/agent-perf-bench/AgentPerfBench) describes `trace_replay` as **result rows** for exact input/output length sequences. Its published methodology uses closed-loop concurrency; CacheFlow V2's primary arrival model is seeded open-loop. We use its reported TTFT, TPOT, ITL, throughput and success-rate definitions as a measurement checklist. We will not call our LoCoMo trace an AgentPerfBench replay or compare raw RTX 3090/Qwen3-1.7B latency with its different model/engine/hardware rows as a leaderboard rank.

## Reproduce the audit

```bash
PYTHONPATH=src python scripts/v2_locomo.py audit \
  --source data/raw/locomo10.json --tokenizer-path <pinned-tokenizer-snapshot> \
  --output results/v2/fit_report.json --output-tokens 64
```
