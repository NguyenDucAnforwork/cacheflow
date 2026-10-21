# CacheFlow

A single-RTX-3090 experiment in LLM inference: vLLM 0.22.0 with GPU prefix caching, LMCache 0.5.3 as a CPU KV tier, and an asyncio ingress scheduler for shared-prefix requests. The model is Qwen3-1.7B BF16 at revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`. This project is inspired by the delay-hit question in [Strata](https://www.usenix.org/conference/osdi26/presentation/xie-zhiqiang); it is not a reproduction of Strata.

## Measured result

- **CPU KV tier helps under pressure.** On the 32-request 8K long-document revisit trace with 6 GiB GPU KV, B1 (GPU cache only) had ~2.59 s mean TTFT on late revisits; B2 (GPU + CPU tier) had 0.33–0.37 s. B2 restored 65,536 prompt tokens from CPU and computed 66,128 new prefill tokens versus B1's 131,664. At 4 GiB, two more matched pairs reduced late revisit TTFT from ~3.0 s to 0.57–0.70 s.
- **Benefit follows working-set pressure.** With eight documents and 8 GiB GPU KV, B1 and B2 both used GPU hits, computed the same prefill tokens, and had ~0.1 s late revisit TTFT; B2 loaded no CPU chunks. With 12 documents at the same 8 GiB budget, B2 restored 98,304 tokens/384 chunks and reduced late revisit TTFT from 5.42–5.70 s to 2.00–2.09 s in two matched pairs.
- **Ingress deferral did not improve cache reuse.** Original DHAS and a later readiness guard produced the same total cached and computed prefill tokens as FIFO in the measured 8K comparisons. The original policy's 200 ms wait expired before producer first-token readiness for all 8K candidates. A same-engine crossover removed an apparent restart-based speedup; the guard's untouched-seed holdout was slower than FIFO by +3 and +98 ms paired mean TTFT in two runs. These are negative results for this configuration, not general claims about scheduling.

All measured prompts, statuses, and output token counts matched within the selected paired audits. Some output-text hashes differed even on same-policy repeats; only hashes were retained, so semantic impact is unknown. LMCache's inclusive retrieve spans were observed, but exact H2D transfer and copy/compute overlap were not instrumented.

## Project map

- [Results and caveats](docs/main_results.md), [design decisions](docs/decisions.md), [ideas](docs/ideas.md), [lessons](docs/lessons_learned.md), and [reproduction steps](docs/reproduce.md) are the five living docs.
- `src/cacheflow/` contains the gateway, bounded admission scheduler, token-aligned prefix fingerprints, deterministic replay, metrics collector, paired analyzer, quality audit, and plot generators.
- `scripts/` contains stack setup, controlled runs, cache-reset crossover, profiler and audit commands. `results/raw/` holds per-request/metrics traces; `results/figures/` contains paired timelines and the [capacity](results/figures/capacity/capacity_boundary.png) and [working-set](results/figures/workingset/workingset_pressure.png) plots.
- `results/registry.csv` and individual `.summary.json` files record run IDs, trace hashes, source commits and parameters. Model weights and credentials are excluded from Git.

The baseline commands and host-specific setup are in [docs/reproduce.md](docs/reproduce.md). All performance claims above refer to the recorded single host and workload, with two run-level repeats where stated.
