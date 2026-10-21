# CacheFlow: lessons and failures

## Methodological lessons from Sunshine_final_report.pdf

- A strong baseline matters: use the same engine settings and workload across arms, changing one mechanism at a time.
- Pair the same request IDs across runs; aggregate throughput can cover different completed-request sets.
- Report the TTFT distribution and validity/errors, not just mean latency or throughput.
- Diagnose CPU, transfer, queue, and GPU phases before attributing latency to kernels.
- A small probe can reject a bad idea but cannot certify an improvement; repeat representative conditions.
- Validate effects in the workload regime where the mechanism acts; include a low-reuse negative control.

Experiments below are development runs; preserve failures and contradictory observations.

## Setup attempts (2026-10-21)

- vLLM CLI initially failed importing `libcudart.so.13`. The library existed in the installed CUDA 13 package; adding its directory to `LD_LIBRARY_PATH` allowed B1 to boot and serve a real request. CUDA/PyTorch ABI compatibility still needs MP and longer-run validation.
- LMCache MP first failed because port 8080 was occupied by the instance image. Restarted its localhost metrics HTTP endpoint on 18080; `/metrics` returned 200. Request port remains 5555.
- LMCache warned that its `c_ops` extension was unavailable and would use torch baseline device ops. Record this in performance interpretation.
- The first B0 launch returned exit code 3 after all required B0 services were healthy because `supervisorctl status` included the intentionally stopped LMCache service. No benchmark started. `scripts/set_mode.sh` now checks vLLM and gateway separately for B0/B1; the B0 run was restarted from a clean mode reset.

## Restore evidence and instrumentation caveat

A large LMCache `l1_read` count alone did not prove an effective CPU restore: the initial repeated request still showed GPU-local prefix hits. Clearing only vLLM's local cache and checking vLLM external hit tokens together with LMCache loaded chunks gave a defensible test. The pinned vLLM version exposes its reset endpoint only with `VLLM_SERVER_DEV_MODE=1`; the server is localhost-only.

## First scheduler screen

The original 32-request long-document trace filled LMCache L1 (~7.5 GiB) but produced zero engine-loaded LMCache chunks. Closely spaced questions reused GPU KV; the trace had no later revisit after GPU eviction. A CPU-tier baseline needs a workload that returns to old prefixes, not just a working CPU-cache process or a cache-full gauge. The one B3 run was ~100 ms faster across every request with unchanged GPU hit and prefill-compute totals, so run-order/thermal effects must be tested before attributing the difference to DHAS.

## Revisit pairs

Adding late requests successfully exercised CPU-tier restores in both B2 and B3. Yet all four arms computed exactly 66,128 prefill KV tokens and recorded 196,608 cached prompt tokens. The first paired B3 run lost ~302 ms on mean per-request TTFT, while the second lost ~31 ms. B2 varied much more across runs than B3. A bootstrap over requests inside one run is too narrow for this between-run variance; report repeated run-level effects and do not treat the request-level interval as a causal confidence interval. The measured scheduler has no demonstrated cache benefit so far.

The 200 ms fairness bound expired for every delay-hit candidate in both revisit runs: median producer-first-token time was ~1.77 seconds after follower arrival. The admission policy paid the hold cost without reaching its first-token readiness condition. A gateway should estimate whether producer readiness can occur inside its latency budget before deferring a follower; a raw shared-prefix match is insufficient.

In the distinct-prefix control, neither B3 run had a delay-hit candidate or any cache hit, yet it trailed FIFO by +75 and +129 ms mean paired TTFT. The scheduler's matching checks and event-loop work may have a measurable cost, but host/engine queue-time drift also changed. Instrument CPU and GPU clock behavior before attributing the entire difference to Python logic.

Repeated tier baselines show a clear CPU-cache mechanism: B1 recomputed 131,664 prefill KV tokens, while B2 computed 66,128 and loaded 256 LMCache chunks, reducing late revisit mean TTFT from ~2.59 s to 0.33–0.37 s. Temperature zero did not make every generated string identical across engine/cache configurations or repeated runs: isolated 1/32 hash mismatches occurred in B0/B1 and B1/B2 comparisons with unchanged 64-token budgets. Report these rather than implying byte-for-byte equivalence across every baseline.

Static grouping was no better than FIFO on the 8K revisit trace, with identical KV hit/compute totals and +31 ms paired mean TTFT. On distinct 2K prompts, its paired mean penalty was +133 ms, again with no cache hit. This simple scheduling control does not explain a missing DHAS gain; admission timing changed without changing the engine's prefix reuse in these conditions.

The 4K multi-turn trace supplied a more promising timing pattern: four of nine inferred follower opportunities reached producer first-token readiness inside 200 ms. Even there, B3 did not change cached-token or computed-prefill totals. A first token is an upper-level readiness hint, not evidence that an asynchronous LMCache store is visible or that vLLM has not already shared the prefix. Output hashes differed on 10/32 matched requests despite identical 64-token budgets; the current hash-only runner cannot judge semantic impact.

The 2K long-document burst made the metric trap concrete. Most inferred candidates could reach producer first token before the policy deadline, but B2 and B3 computed the same 16,976 prefill KV tokens. vLLM server-side TTFT was lower under B3, while arrival-based TTFT was higher by +82 ms paired mean because deferral happened before engine admission. Always present both clocks; engine-only latency would falsely suggest a win.

Two restart-based simultaneous 8K pairs appeared to favor DHAS by 246–385 ms on mean TTFT, yet all 32 request deltas in each pair shifted almost uniformly, including leaders, without any change in cached or computed prefill tokens. A stronger ABBA crossover held the same vLLM/LMCache PIDs, warmed them equally, verified empty caches, and switched only the gateway. It gave opposing B3 effects of −92 and +109 ms. This rejects a reproducible latency win under the tested trace and shows why run-level controls matter more than very narrow request-level bootstrap intervals from one run.

LMCache's OTLP profiler was usable without Nsight or a new collector dependency: a small local gRPC sink recorded 124 spans, including eight real CPU-tier retrieve operations. Their inclusive median duration was ~149 ms for 896 MiB each. The installed 0.5.3 build did not emit separate transfer staging/kernel spans described by newer documentation, so exact H2D time and true copy-engine overlap are still unmeasured. Do not turn an inclusive retrieve interval into a PCIe bandwidth claim.

The online readiness guard bypassed six and four of ten inferred long-prefix follower waits on two development runs, cutting bypassed-candidate gateway waiting to about 20 ms. Its end-to-end paired mean TTFT was −211 ms then −3 ms versus FIFO, with cache and prefill work exactly unchanged. Guarded-vs-original effects even flipped sign across bracketing runs. A local policy action can be real without producing a stable user-visible gain; run-level crossover and an untouched seed are required before claiming one.

The frozen guard failed its untouched-seed holdout. It skipped four futile waits in each seed 11 run, but full-run paired TTFT was +3 and +98 ms versus FIFO and +111 and +118 ms versus original DHAS. Total cache hits and computed prefill work were identical across all six arms. A reduction in a local queue phase can be offset elsewhere in a concurrent engine; keep the local mechanism finding and the negative user-facing result separate. One guarded arm also moved 6,464 hit tokens from CPU to GPU while leaving total cached tokens fixed, illustrating why a total cache-hit counter alone is insufficient for tier attribution.

At 4 GiB GPU KV, two independent B1/B2 pairs had 65,536 CPU-restored tokens and 256 loaded chunks per B2 run, cutting late revisit mean TTFT from ~3.0 s to 0.57–0.70 s. At 8 GiB, B1 and B2 each computed 66,128 prefill tokens and B2 loaded no CPU chunks; late revisit latency was ~0.1 s in both. CPU-tier usefulness follows working-set pressure. A populated LMCache L1 gauge (~7 GiB even in the 8 GiB fits) does not mean the tier was read; use load and external-hit deltas. The earlier 6 GiB rows were measured at a different source/time checkpoint, so avoid treating a smooth line through 4/6/8 as a controlled continuous response curve.
