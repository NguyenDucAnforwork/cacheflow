# CacheFlow: lessons and failures

## Methodological lessons from Sunshine_final_report.pdf

- A strong baseline matters: use the same engine settings and workload across arms, changing one mechanism at a time.
- Pair the same request IDs across runs; aggregate throughput can cover different completed-request sets.
- Report the TTFT distribution and validity/errors, not just mean latency or throughput.
- Diagnose CPU, transfer, queue, and GPU phases before attributing latency to kernels.
- A small probe can reject a bad idea but cannot certify an improvement; repeat representative conditions.
- Validate effects in the workload regime where the mechanism acts; include a low-reuse negative control.

No CacheFlow experiment has run yet. Record failed attempts and their fixes here as they occur.
