# CacheFlow: lessons and failures

## Methodological lessons from Sunshine_final_report.pdf

- A strong baseline matters: use the same engine settings and workload across arms, changing one mechanism at a time.
- Pair the same request IDs across runs; aggregate throughput can cover different completed-request sets.
- Report the TTFT distribution and validity/errors, not just mean latency or throughput.
- Diagnose CPU, transfer, queue, and GPU phases before attributing latency to kernels.
- A small probe can reject a bad idea but cannot certify an improvement; repeat representative conditions.
- Validate effects in the workload regime where the mechanism acts; include a low-reuse negative control.

No CacheFlow experiment has run yet. Record failed attempts and their fixes here as they occur.

## Setup attempts (2026-10-21)

- vLLM CLI initially failed importing `libcudart.so.13`. The library existed in the installed CUDA 13 package; adding its directory to `LD_LIBRARY_PATH` allowed B1 to boot and serve a real request. CUDA/PyTorch ABI compatibility still needs MP and longer-run validation.
- LMCache MP first failed because port 8080 was occupied by the instance image. Restarted its localhost metrics HTTP endpoint on 18080; `/metrics` returned 200. Request port remains 5555.
- LMCache warned that its `c_ops` extension was unavailable and would use torch baseline device ops. Record this in performance interpretation.

## Restore evidence and instrumentation caveat

A large LMCache `l1_read` count alone did not prove an effective CPU restore: the initial repeated request still showed GPU-local prefix hits. Clearing only vLLM's local cache and checking vLLM external hit tokens together with LMCache loaded chunks gave a defensible test. The pinned vLLM version exposes its reset endpoint only with `VLLM_SERVER_DEV_MODE=1`; the server is localhost-only.
