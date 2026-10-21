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
