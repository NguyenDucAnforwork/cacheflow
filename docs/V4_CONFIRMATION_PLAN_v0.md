# V4 prospective confirmation and full-benchmark protocol

**Frozen candidate/protocol:2026-10-26, before any V4 GPU evaluation of conv43/44.** Source fingerprints and exact parameters are in `results/v3/v4_method_freeze.json`. Ongoing development validation can reject this configuration; it does not authorize silent retuning. This freeze is not a completion claim. Existing development/pilot results remain labelled development.

## Candidate and common preparation

`packing_reuse`: reserve the union of active exact16-token causal-prefix blocks, plus each request's incomplete tail,96 output tokens and16-token safety page, rounded to16. Oldest feasible request first; allow first feasible backfill with at most8 bypasses of the current ingress head. Active-empty always starts the oldest request. Packing applies when a queued prefix group matches active/recent work; otherwise use FIFO. This is logical reuse opportunity, not a GPU/CPU-residency oracle. It controls admission/order, not allocator, KV validity, prefetch or a forced restore/recompute choice.

Gateway max-inflight64; max-queue64 for <=60-request dev/held-out,512 for full1986. One serial CPU preparation worker, exact tokenizer ids and both fingerprints, fresh local upstream connections, no retries. Scheduled-arrival TTFT includes preparation/worker waits, gateway admission, transport/pool waits, native queueing and execution. The bypass bound is before handoff; it is not an E2E latency guarantee.

Model Qwen3-4B BF16, revision `1cfa9a7208912126459214e8b04321603b3df60c`, maximum context32768,96-token generation cap, temperature0, text-only full histories, no reasoning/answer extraction. Prompt `locomo-qwen-concise-v4` globally requests `No information available.` for absent answers. No per-question gold, evidence label or future arrival enters admission.

## Resource and implementation regimes

| Regime | GPU KV | CPU KV | Native maximum requests | Chunked/batched prefill |
| --- | ---: | ---: | ---: | ---: |
| Main pressure dev/held-out |6GiB|16GiB|16|8192tokens|
| Dev GPU-fit |10GiB|16GiB|16|8192tokens|
| Full primary |6GiB|48GiB|16|8192tokens|
| Full larger-cache control |10GiB|48GiB|16|8192tokens|

Conservative union capacities43664/72800 tokens for6/10GiB. Same budget applies to all arms in a regime. Full common-prefix footprint34.031GiB motivates48GiB CPU; private state is additional/evictable. Full and dev are separate memory regimes.

SGLang0.5.14, kernel0.4.4+cu129, FlashInfer0.6.12, Direct/page_first_direct, write-through, decode graphs. Same-batch guard threshold100 is enabled for all guarded arms; it is a component adaptation of Strata4.3.1, not the complete published system. It does not implement full transient nodes, balanced batches or bubble filling. Profiling disabled in performance runs. Native in-batch check/deprioritize thresholds32/32. Record resolved config, actual env, source/overlay hashes and PID.

Main stack vLLM0.22.0 + LMCache0.5.3, CUDA graphs/maxseq16/batch8192/chunk256, serial preparation across every arm. Batch-invariant and heavy/event profilers disabled. Real byte-hash KV publisher/subscriber is enabled uniformly where comparing actual-GPU LPM; verify namespace and zero sequence gaps.

## Baselines fixed before confirmation

SGLang primary comparison uses identical LPM+guard backend: native direct, FIFO64 gateway and union64 gateway. Native DFS-weight+guard is an additional strong competitor, particularly for full queues where native LPM falls back to FCFS above128. Report cross-policy/fresh-process comparisons separately from same-backend crossovers. No full-Strata reproduction or latest-all-policy SGLang claim.

Main-stack dev uses FIFO16/FIFO64, actual-GPU LPM16, bundle16, fixed200ms DHAS16 and union64. Held-out main comparisons use FIFO64, bundle16 and union64. Bundle is a limited wave/grouping adaptation, not complete Strata. Native/kernel baselines may use a stronger tuned implementation than a simple gateway heuristic; do not omit them when reporting wins.

## Fresh confirmation

Conversations43/44, first20 original QA each:40 questions. Seeds701/702/703; primary exponential4QPS, secondary2QPS. Generate exact V4 traces only after this source/protocol freeze. CPU trace preparation alone is not GPU evaluation. No method/config decision after observing these runs.

SGLang primary4QPS: native LPM+guard, FIFO64+LPM+guard, union64+LPM+guard, and native DFS-weight+guard. Secondary2QPS: native LPM+guard versus union64+LPM+guard. Main-stack4QPS: FIFO64, bundle16, union64. Three balanced run-level repetitions per primary contrast; reverse/permutate order by seed. Preserve process/source differences and compare exact trace/prompt hashes. Start each arm with empty GPU/CPU cache and fresh gateway scheduler state. Warm code with dev prompts or a uniform tiny warmup before the reset, not a hidden hot held-out prefix.

## Full evaluation

All1986 fit QA, all ten conversations, fixed V4 prompts and original annotations. Exponential4QPS, seeds901/902/903. Primary SGLang6GiB/CPU48GiB arms: native LPM+guard, FIFO64+LPM+guard, union64+LPM+guard, native DFS-weight+guard. Rotate/reverse arm order across seeds. A10GiB/CPU48GiB native-LPM/union pair is a separate resource control, initially seed901; do not claim repeated no-regression from one pair. A main-stack full seed901 comparison may supplement the primary study; do not describe a single seed as replicated cross-engine evidence.

The supplied arrival processes are synthetic, not production logs. Report per-run p50/p95/p99, makespan/achieved throughput, failures, prompt/source token accounting, native queue and gateway waits, memory/resource samples, head bypass and per-conversation latency. Do not infer saturation throughput when arrivals limit it.

## Audit, profiling and acceptance

Every run requires complete success and output capture, exact trace/token/prompt identity, proper budgets, source/config/env proof, successful empty-cache reset and fresh gateway history. Errors or ownership/source mismatches invalidate a performance run; no success-only percentiles, hidden retry or overwritten run IDs. Keep partial/error artifacts.

Grade raw outputs with the pinned original evaluator, retaining category5 separately from answerable F1. Report output-cap hits and all hash/score differences. Ordinary temperature0 is not bit-exact batching; the earlier batch-invariant diagnostic has a separate scope. Do not assert broad quality equivalence from near-equal means or treat repeated seeds as new QA. Inspect full category and paired score changes before a quality claim.

Primary claim is conditional improvement under memory pressure, especially versus FIFO and tuned grouping, with source-labelled mechanism and preserved operational correctness. Require >=3 run-level repetitions for key claims and no >5% low-reuse p95 regression for the declared low-reuse control. Report p50 tradeoffs and GPU-fit failures explicitly. A configuration that merely moves delay outside engine TTFT does not pass. No universal no-regression or SOTA claim follows from a small dev win.

Profile separately with CPU-hot off/GPU-only-profiler/off calibration, CUDA events and a kernel/copy timeline where feasible. Forward-span overlap is not useful model-kernel overlap. Profiling runs never replace unprofiled latency. Full results, reproduction commands, limitations and Vietnamese interview explanations remain required deliverables.
