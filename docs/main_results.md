# CacheFlow: live results

Status: specification and environment audit complete; no model or benchmark has run. All performance cells are intentionally unmeasured.

## Host audit (2026-10-22)

| Item | Observed |
| --- | --- |
| GPU | GeForce RTX 3090, 24 GiB; idle at audit |
| CPU RAM | 247 GiB total, 183 GiB available at audit |
| Workspace disk | 20 GiB available initially; overlay filesystem |
| Workspace volume | false; sync code and results off-instance before recycle/destroy |
| Python / PyTorch | Python 3.12.3; torch 2.11.0+cu128 in /venv/main |
| vLLM / LMCache | not installed at audit |
| Git repository | absent at audit |

## Primary comparison

| Arm | Stack | Fixed-arrival result | CPU KV restore proof |
| --- | --- | --- | --- |
| B0 | vLLM, prefix cache off | pending | N/A |
| B1 | vLLM, GPU prefix cache on, FIFO | pending | N/A |
| B2 | B1 + LMCache CPU tier, FIFO | pending | pending |
| B3 | B2 + DHAS gateway | pending | pending |
| B4 | B2 + static prefix grouping (if affordable) | pending | pending |

Primary contrast is B3 vs B2 with identical engine, trace, model, token/output budgets, and cache pressure. Record arrival-based TTFT p50/p90/p99, TPOT, output tokens/s, requests/s, errors, GPU/host cache-hit tokens, CPU RAM, GPU memory/utilization, and scheduler queue wait. Report paired per-request deltas and repeat key conditions at least twice. A negative result is valid.

## Evidence gate

Do not label a request as CPU-restored from a prefix match alone. Require GPU-local eviction/absence plus LMCache L1 read or load counters and vLLM host-source cached token evidence if exposed by pinned versions. Missing metrics are marked not instrumented. Keep raw traces and exact Git SHA for every result.
