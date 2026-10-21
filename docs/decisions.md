# CacheFlow: design decisions and execution plan

## Scope and provenance

Single GPU, Qwen3-1.7B BF16 target, vLLM plus LMCache MP CPU tier, and an ingress-only Delay-Hit-Aware Admission Scheduler (DHAS). Inspired by Strata's delay-hit problem, not a Strata reproduction. Sunshine_final_report.pdf informs methodology: strong baseline, paired request comparisons, one-variable ablations, profiling across CPU/GPU boundaries, and explicit failure analysis. Its H200/SM90 mechanisms and scores do not transfer to the RTX 3090 study.

## Architecture

Fixed-schedule replay client -> local streaming gateway -> one vLLM OpenAI-compatible server -> LMCache MP server with bounded CPU L1. The gateway forwards the original request body and does not alter prompt, decoding parameters, or response content. It tokenizes for metadata using the exact pinned model tokenizer and verifies token counts against vLLM. Use completion prompts with deterministic chat/session formatting to make prefix matching auditable. Hash full block-aligned token-ID prefixes with a keyed or stable digest; store hashes and lengths only, never raw prompts in logs.

Gateway policies: FIFO, static grouping, DHAS. DHAS tracks in-flight producer prefix groups, estimates a potential delay hit, and holds a compatible follower until producer first content token plus a measured cache-store grace, or until its hard deadline. Defaults for screening: minimum shared prefix 1024 tokens, max wait 200 ms, queue cap 64, age-based admission, per-request cancellation/timeout propagation. These values are hypotheses, tuned on development traces only. If ready signal or store completion is not observable, use a bounded-window policy and record that limitation.

## Experimental contract

B0: vLLM no prefix cache; B1: vLLM GPU prefix cache + FIFO; B2: B1 + LMCache CPU tier + FIFO; B3: identical B2 engine with DHAS; B4: identical B2 with static grouping if time permits. A causal claim requires B3 vs B2. Test multi-turn sessions, long-document QA bursts, and distinct-prefix negative control. Use 2k–8k input tokens, 64–128 output tokens, fixed arrivals and temperature 0. Select a compact 6–10 condition matrix spanning locality, concurrency, and GPU cache pressure. Warm/cold state and GPU eviction must be evidenced, not assumed.

Log per request: scheduled arrival, gateway receipt, enqueue, dispatch, first content token, finish, status, prefix digest/length, token counts, deadline, and policy decision. Use one host monotonic clock for replay and gateway. Distinguish scheduled-arrival TTFT from vLLM server TTFT. Capture vLLM and LMCache metrics with pinned metric names, plus CPU/RAM and GPU/VRAM telemetry. Build a request timeline and one transfer/compute overlap figure if instruments permit. Compare paired request IDs, repeat high-value arms >=2 times, and report uncertainty and failures.

## Hard gates and timebox

1. T+0–40 min: disk/ABI and version compatibility, exact model revision, repo and five living docs, model cache plan. Existing 20 GiB overlay and non-volume workspace require disk checks and frequent pushes.
2. T+40–90 min: server smoke, B1/B2 cold/warm test, confirmed CPU restore. If MP fails beyond T+75 min, document and use an explicitly labeled in-process fallback.
3. T+90–140 min: fixed replay and B0/B1/B2, metrics, pressured cache regime.
4. T+140–215 min: implement and test scheduler, first B3 screen.
5. T+215–285 min: paired B2/B3 plus static control and negative control, profile one short trace.
6. T+285–360 min: root cause, at most one refinement, freeze, report and push; stop paid GPU processes.

At T+120 min without a reliable two-tier baseline, narrow to a measured KV-tiering study and record the scope change. At T+270 min, freeze architecture and dependencies. GPU runtime budget is 3–4 hours within the six-hour wall-clock sprint.

## Sources and open decisions

- Strata (OSDI 2026): https://www.usenix.org/conference/osdi26/presentation/xie-zhiqiang
- LMCache MP quickstart and compatibility: https://docs.lmcache.ai/getting_started/quickstart.html and https://docs.lmcache.ai/getting_started/compatibility.html
- LMCache metrics: https://docs.lmcache.ai/mp/observability/metrics.html
- vLLM metrics: https://docs.vllm.ai/en/latest/usage/metrics/

Pin versions only after verifying Python/Torch/CUDA ABI and a live Qwen3-1.7B smoke test. Current LMCache docs note that the LMCache-shipped MP connector requires vLLM >=0.20.0 and explicit kv_connector_module_path; this is a validation gate, not an assumed installed stack. Confirm exact metric names after installation.

## Metric implementation notes (pre-install review)

After pinning versions, inspect live `/metrics` names. Current vLLM docs list `vllm:prompt_tokens_cached_by_source` (device vs host), `vllm:request_prefill_kv_computed_tokens`, `vllm:request_queue_time_seconds`, and `vllm:time_to_first_token_seconds`. Current LMCache MP docs list L1 read/write/eviction counters, `lmcache_mp.num_chunks_loaded`, submitted/finished retrieve counters, and L0↔L1 throughput histograms. A transfer completion counter alone does not prove bytes were restored; use loaded chunks and tier-source tokens together.

## Stack pin (2026-10-21 17:48 UTC)

Use vLLM 0.22.0 + LMCache 0.5.3 + transformers 5.6.2 with the image's torch 2.11.0+cu128. vLLM's wheel links CUDA 13 runtime libraries even though the base PyTorch wheel is cu128; `LD_LIBRARY_PATH=/venv/main/lib/python3.12/site-packages/nvidia/cu13/lib` is required before CLI launch. The B1 smoke succeeded with this combination, but MP interoperability remains to be proven. Set GPU KV budget to 6 GiB (vLLM reported 56,160 tokens), CPU L1 to 16 GiB, model length 12,288, and max sequences 16. All compared arms will use these engine settings.

## Runtime controls (2026-10-21 17:56 UTC)

Supervisor manages `cacheflow_lmcache`, `cacheflow_vllm`, and `cacheflow_gateway`, all bound to 127.0.0.1. `scripts/set_mode.sh` selects B0/B1/B2/B3/B4 and gateway policy, restarts services, and checks health. vLLM dev mode is enabled solely on localhost to permit local GPU prefix-cache reset without clearing LMCache; this provides a direct CPU restore validation. For controlled benchmark cold resets, restart both vLLM and LMCache, then use the same warmup procedure in each arm. Current restore probe confirms the MP path; benchmark pressure remains to be measured.

## Workload revision after evidence (2026-10-21 18:03 UTC)

The first long-doc burst never revisited a document after enough distinct documents filled GPU KV. It is retained as a development screening trace. Add `long_doc_revisit`: hold the final question for each document until after the first wave, then revisit early documents after likely GPU eviction while LMCache CPU L1 remains populated. Use the same deterministic trace and cold reset in both arms. Verify actual external hit counters before calling it a CPU-pressure condition. Development seed 7 may guide window tuning; reserve a different seed for final holdout.

## Mechanism and profiler choice (2026-10-21 18:36 UTC)

The 8K gateway traces show that the 200 ms defer bound expires before producer first-token readiness for all measured delay-hit candidates. Preserve that bound for fairness instead of extending it to ~1.8 seconds to force a cache event. Run a 2K positive-locality probe and multi-turn sessions before trying one refinement that predicts infeasible waits. The static grouping control and low-reuse negative control are retained even though they did not improve latency.

Nsight Systems is absent on this rental. The pinned LMCache MP server supports OTLP tracing, and its official tracing reference describes `mp.retrieve`, `transfer.kernel_interval`, and `transfer.staging` spans. Capture one separate B2 profiling run with a localhost OTLP gRPC sink; do not mix tracing-overhead timing into the B2/B3 performance pairs. LMCache's broad `/metrics` counters and 1-second GPU sampler remain the main low-overhead instruments. Exact H2D time remains uninstrumented unless the transfer staging spans appear in the pinned build.

`max_wait_ms` bounds the policy's intentional delay: at the deadline the ticket becomes eligible. Actual arrival-to-dispatch wait can exceed it when `max_inflight` is full or ingress preparation is delayed. Record the admission deadline and any overrun separately from first-token and total TTFT rather than describing 200 ms as an end-to-end queue cap.

## Live-engine crossover after repeated run offsets (2026-10-21 18:51 UTC)

The two simultaneous 8K pairs showed large nearly uniform TTFT shifts across all 32 requests in an arm, including leaders that DHAS does not intentionally defer. A restart-based pair therefore may mix engine/host drift with scheduler effects. The installed LMCache MP API exposes `POST /cache/clear`, and vLLM's localhost dev endpoint exposes `POST /reset_prefix_cache`. With all requests idle, clear L1 and GPU prefixes, warm the same live engine with a fixed two-request probe, clear again, and restart only the gateway when switching FIFO/DHAS. Use ABBA order on one engine process, verify zero L1 bytes and identical computed-prefill/cached-token totals, and compare gateway and engine phases. This adds a second control design; retain the cold-restart results rather than overwriting them.

The live-engine ABBA result was −92 ms then +109 ms paired mean B3−B2 TTFT with identical cache and prefill work. The original delay-hit benefit is not supported in this vLLM/LMCache configuration. Continue with one bounded refinement aimed at avoiding waits known to expire, then run an untouched-seed holdout. Preserve all negative-control data and report B2's real CPU-tier benefit separately from the DHAS result.

The separate OTLP profile captured `mp.retrieve` operation intervals and byte counts but no transfer staging/kernel sub-spans in LMCache 0.5.3. Keep the profiler artifact and report H2D as not instrumented. No Nsight installation is warranted on this rental.
