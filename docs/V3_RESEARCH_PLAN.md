# V3 competitive research execution

Started 2026-10-26 05:59 UTC; user explicitly requires **at least five additional hours** of work (earliest completion ~10:59 UTC), a materially stronger research contribution, comparison against strong relevant baselines, thorough profiling and complete documentation including `docs/INTERVIEW.md` for inference-engineer interview preparation. Five hours is a minimum, not a success criterion. The previous V2 results are mechanism baselines and do not meet this new objective.

## Requirements and completion evidence

1. Align the method with proposal RQ0/RQ1/RQ2/RQ3; identify an opportunity through real profiling before claiming a new admission/cache policy. Existing fixed-DHAS negative results remain valid in their tested regimes.
2. Review recent primary papers (window 2025-04-26 through 2026-10-26), original code and practical hardware constraints. Distinguish exact implementations, faithful adaptations and heuristic controls. Never label a small heuristic as a complete paper reproduction.
3. Compare with strong baselines under matched model, prompts, budgets, quality, arrival schedule and hardware resources. Include tuned engine/admission controls and, where runnable, an original recent-paper implementation. Record incompatible systems and preserve evidence rather than inventing results.
4. Profile request preparation, queueing, prefill/decode, cache lookup, actual H2D/D2H transfer and CPU/GPU resource occupancy. Instrumentation overhead is measured separately from final unprofiled comparisons.
5. Develop a testable, falsifiable contribution; screen on dev, freeze method/config before new confirmation traces, run >=3 balanced repetitions for key claims, include low-reuse/GPU-fit/load controls and ablations. No failed requests or omitted waiting time may count as a latency win.
6. Capture and grade outputs with a viable chat prompt and identical budgets; preserve all mismatches. Avoid source-answer/evidence leakage and do not claim full-LoCoMo accuracy for subsets.
7. Write reproducible research documentation and **Vietnamese `docs/INTERVIEW.md`**: accessible architecture explanation, calculations, real profiling evidence, method/baseline rationale, limitations and substantial project-specific interview questions with explained answers.
8. Preserve prior results and the separate V1 worktree. Push code/docs/small summaries; keep raw traces/profiles/model weights ignored and retained locally. Finish only after >=5 hours and current-state evidence proves the research and documentation requirements.

## Initial directions (not measured contributions)

- Recent methods to inspect: Strata (OSDI 2026), Cake (ICML 2025), LPC (NeurIPS 2025), EpiCache (ICML 2026). Primary-source evidence and applicability are recorded in a literature/baseline matrix.
- Candidate opportunities: excessive queued long-context KV reservations; restore/compute overlap; bounded residency-aware grouping that saves actual CPU transfers without low-reuse/tail regressions; unnecessary CPU backup/lookup on GPU-fit or one-shot requests. Choice depends on profiling.
- The prior raw-completion template is insufficient for primary QA claims. A chat-formatted, concise-answer protocol and frozen evaluator will be specified before new competitive measurements.

## Live execution

Branch `feat/cacheflow-v3-competitive` created after fetching origin. Baseline environment passes 21 tests and preflight. V2 services were stopped at kickoff. Serving dependencies will stay intact; any external engine is isolated. Current-host constraints include one RTX 3090 (SM86), 24 GiB VRAM, ~14 GiB free overlay disk, and no kernel-level profiling privileges.

### Checkpoint ~06:26 UTC

- New concise chat protocol frozen as `locomo-qwen-concise-v3`, 96-token output cap, no answer extraction, dev conv-26/30/41 first 20 QA each, seed 101, nominal QPS 0.5/1/2; low-reuse control uses one QA per dev conversation. Conversation-disjoint fresh V3 confirmation will be fixed before tuning the candidate, including conv-43/44 which were not GPU-evaluated in V2.
- First low-load FIFO cap16 vs cap1 screen has effectively identical compute/transfer and p95, so cap tuning alone is not counted as contribution.
- One instrumented dev profile captured PyTorch CUDA kernel timeline and opt-in LMCache MP event callbacks. Actual host link is PCIe Gen3 x16. 56 H2D events transferred ~121.7 GB in 10.73 summed seconds; median event bandwidth ~11.35 GB/s. The CUDA profile covers the early/cold part, not all steady-state transfers. Profiling inflates p95 (31 s vs ~3.57 s unprofiled); never use that profile latency as a performance result.
- Lightweight source-token counters and per-phase gateway timers are in place. FIFO vs LPM-hint and oldest-bundle admission baselines are being screened before a proposed method. LPM-hint is an external approximation, not SGLang's true residency lookup; bundle-wave is a limited adaptation of oldest-first bundle selection, not complete Strata.
- SGLang 0.5.14 / matching kernels / isolated transformers install remains live (tool session 86551; uv PID 61198). Download/unpack byte counters are progressing. Do not restart merely because the log is quiet.
- Current profile and diagnostic scripts retain exact request IDs for CPU/GPU event correlation. Initial legacy diagnostic `v3-profile-screen-fifo16-chat-val-s71` lives in V2 raw/registry as a clearly named carryover; subsequent V3 runs use the separate V3 tree.

### Opportunity gate and candidate design, ~06:54 UTC

Three same-engine seed contrasts at nominal 2 QPS now demonstrate actual transfer work and arrival-latency opportunity for cache-aware ordering. Oldest-first bundle-wave vs FIFO at cap 4 reduces p95 by **35.77%, 29.88%, 14.36%** on seeds 101/102/103, with lower actual external KV tokens. LPM-hint substantially reduces transfer and median TTFT but has a p95 regression on seed 102. These are baseline mechanism results, not a new contribution or complete Strata reproduction. The old fixed-DHAS delay-hit claim remains unsupported.

Proceed to a **residency-aware memory admission** candidate: reserve the union of active requests' exact shared KV blocks plus unique suffix/output budget, permit compatible work while avoiding unnecessary CPU-backed context migration, and bound bypass of the oldest request. Cold/low-reuse work should fall back to engine scheduling when there is no verified reuse opportunity. Use real vLLM KV events when possible rather than assuming the last context is resident; an actual-residency LPM baseline receives the same event information. Compare to tuned FIFO, LPM, bundle-wave and upstream HiCache, then ablate packing, residency information and bypass guard. No hidden prompt/output changes or future arrivals/QA labels may enter decisions. Fresh confirmation traces remain untouched.

An isolated SGLang 0.5.14 install completed successfully after a slow but progressing kernel-wheel download. Runtime dependency verification is ongoing; successful installation is not yet successful serving. Qwen3-4B is separately downloading at pinned revision `1cfa9a7208912126459214e8b04321603b3df60c`; all shard sizes/SHA256 must verify before adoption. No 4B GPU result exists yet.

### Live hash-contract audit, ~07:18 UTC

The first IPC-event screens received events with zero gaps but predicted zero GPU matches. A direct store-payload probe established that vLLM defaults to legacy **integer 64-bit external hashes**, whereas the gateway index used full SHA256 byte keys. Matching the internal hash function alone did not validate this external representation. All `v3-real-*` screens are diagnostic-only and excluded from valid comparisons by `residency_namespace_diagnostic.json`; raw outputs remain retained. The runtime now explicitly sets `VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=0`, and the subscriber verifies block size, key type and the hash of one actual store payload before accepting residency measurements. Health exposes verification and task failure; failed observers invalidate residency evidence. Twenty-seven tests pass, including legacy-int rejection.

### Tuned-engine gate, ~07:29 UTC

Verified byte-hash dev seed101 screens (60 QA each, eager maxseq4): FIFO4 p95 15.291s; actual-residency LPM4 17.641s; packing-only4 4.539s; migration-gated residency4 6.832s; bundle-wave4 9.410s. All observer checks pass with zero gaps. Packing-only beats the extra residency variant on this seed: additional state is not presumed beneficial. These are exploratory, not candidate confirmation.

A stronger vLLM configuration is now live: CUDA graphs enabled, max_num_seqs16, batched-token budget8192, same model/KV/CPU budgets and event publisher. A fixed tiny 4-token engine warmup precedes the crossover; caches clear before each run. The first tuned FIFO16 p95 is **4.235s**, substantially below eager FIFO. This invalidates any claim that the old 15s FIFO result alone establishes a strong contribution. Compare packing and all other arms on this tuned engine before freezing a method. `setup_engine_audit.json` verifies actual engine arguments against the declared runtime.

Resource sampler correction: process metrics now include descendants (engine core, LMCache workers), whereas earlier per-service fields only counted parents. Sum-of-process RSS double-counts shared pages and is not physical memory usage. Final comparisons use the same updated sampler across arms. LMCache transfer histogram summaries are event-average bandwidth values, not total transfer time; do not reinterpret arithmetic throughput sums as byte totals.


### Stronger-model adoption and live matrix, ~07:50 UTC

Qwen3-4B revision `1cfa9a7208912126459214e8b04321603b3df60c` is fully downloaded and all shard SHA256 checks pass; adoption is recorded. Refreshed primary HF range URL resumed existing pieces after a validated Content-Range probe, without discarding completed data. Model-specific dev traces at QPS2/4 and seeds101/102/103 are generated with its pinned tokenizer; no confirmation run is evaluated. The serving preflight rechecks all 4B SHA values and index coverage.

4B screening uses 6GiB GPU KV (43,680 physical tokens, 43,664 reservation budget after null-block allowance), CPU16GiB, CUDA graphs, maxseq16 and batch8192. The 4B GPU-fit budget, if used later, is 10GiB (72,800 conservative tokens). These budgets follow the model's 144KiB/token geometry; 4GiB would not support the chosen 32K maximum context. Do not interpret cross-model timing as changing model size alone. The dev matrix screens FIFO16/FIFO4, packing4/packing16, actual-LPM16, residency16 and bundle-wave16 at QPS2/4, seed101. Fixed tiny warmup and per-run reset remain in place. Candidate/config remain unfrozen.

Three valid native HiCache/LPM dev runs now exist and are graded; seed101/102/103 p95=6.939/8.983/7.761s, p99=7.546/11.222/10.543s. Backend tuning is still required. Current native Triton configuration has decode graphs and auto-disabled prefill graphs, recorded from the resolved server configuration. Native timer/source semantics remain separate from vLLM counters.

First 4B FIFO16 dev QPS2 run completed: 60/60 success, exact prompt-token agreement, actual engine configuration audit passed, F1 **0.3146727492**, 3/60 cap hits, p95 **25.305s**, p99 **26.102s**. This meets the stronger-model feasibility/quality opportunity, not the final method gate. Remaining arms are still running in tool session20750; inspect its actual state before changing any engine process.

### Reliability and CPU admission profile (~08:03 UTC)

The exploratory 4B cap16 grouping screens expose HTTP502/upstream-connect failures: packing16 59/60, residency16 58/60, bundle16 59/60 at QPS2. These runs are explicitly invalidated and never compared on their successful-only percentile. FIFO16/FIFO4/LPM16 and packing4 completed60/60 in that condition. Richer HTTP error detail and gateway exception type are now captured for subsequent runs; the failure cause is still unproven. Do not retry invisibly or replace the failed artifacts.

A CPU-only diagnostic at trace-derived prefix sizes (4 active,50 queued,50 recent; synthetic token contents) profiles packing decisions. Median instrumented `_choose` cost is12.85ms; repeated active-union construction dominates, with additional unused residency scans. This is a microprofile, not an E2E latency result. It motivates reusing the active-block union and skipping information the packing policy does not consume, then verifying selection equivalence and rerunning matched GPU experiments. Do not modify the still-running matrix's policy implementation mid-run.

### CPU implementation and matched dev replications (~08:18 UTC)

After the first14-arm matrix terminated, packing reservation was optimized without changing selection: form the active-block union once, count each candidate's set difference, skip unused GPU/history scans, and reuse a choice while its queue/active/bypass state is unchanged. LPM and migration-gated variants also cache choices with the KV-event sequence included. Tests cover both state invalidation and the exact reservation formula. A pinned-prototype equivalence check matches270 choices;30 unit tests now pass.

Unprofiled CPU microbenchmark at4 active/50 queued/50 recent gives old/new-uncached/new-repeated median12.06/4.57/0.0058ms. This is not an E2E speedup. Actual CPU time and decision-cache hits are exported separately from wall time. Two post-optimization packing16 GPU diagnostics complete60/60 at QPS4, p95~23.6s with either128 or0 retained upstream connections. Thus old socket reuse is only a hypothesis for ReadError, not an established sole cause. Final dev replications standardize on fresh local connections, no retries, same setting for every policy. Any failed run now receives an invalid marker and stops ordinary matrices; explicit diagnostics can continue while remaining invalid.

Next dev crossovers: Qwen3-4B,6GiB KV,16GiB CPU,maxseq16,batch8192,CUDA graphs,QPS4,seeds101/102/103; policies FIFO16,actual-LPM16,bundle-wave16,packing16 and original fixed-DHAS16. Seed102 reverses arm order;103 permutes it. Candidate is still not frozen and fresh confirmation stays untouched. New source/config hashes are recorded per run. Native HiCache4B/backend tuning and controls remain required before confirmation.
