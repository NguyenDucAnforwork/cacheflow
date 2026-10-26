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
