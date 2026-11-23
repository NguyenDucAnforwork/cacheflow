# CacheFlow

A single-RTX-3090 experiment in LLM inference: vLLM 0.22.0 with GPU prefix caching, LMCache 0.5.3 as a CPU KV tier, and an asyncio ingress scheduler for shared-prefix requests. The model is Qwen3-1.7B BF16 at revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`. This project is inspired by the delay-hit question in [Strata](https://www.usenix.org/conference/osdi26/presentation/xie-zhiqiang); it is not a reproduction of Strata.

## Measured result

- **CPU KV tier helps under pressure.** On the 32-request 8K long-document revisit trace with 6 GiB GPU KV, B1 (GPU cache only) had ~2.59 s mean TTFT on late revisits; B2 (GPU + CPU tier) had 0.33–0.37 s. B2 restored 65,536 prompt tokens from CPU and computed 66,128 new prefill tokens versus B1's 131,664. At 4 GiB, two more matched pairs reduced late revisit TTFT from ~3.0 s to 0.57–0.70 s.
- **Benefit follows working-set pressure.** With eight documents and 8 GiB GPU KV, B1 and B2 both used GPU hits, computed the same prefill tokens, and had ~0.1 s late revisit TTFT; B2 loaded no CPU chunks. With 12 documents at the same 8 GiB budget, B2 restored 98,304 tokens/384 chunks and reduced late revisit TTFT from 5.42–5.70 s to 2.00–2.09 s in two matched pairs.
- **Ingress deferral did not improve cache reuse.** Original DHAS and a later readiness guard produced the same total cached and computed prefill tokens as FIFO in the measured 8K comparisons. The original policy's 200 ms wait expired before producer first-token readiness for all 8K candidates. A same-engine crossover removed an apparent restart-based speedup; the guard's untouched-seed holdout was slower than FIFO by +3 and +98 ms paired mean TTFT in two runs. These are negative results for this configuration, not general claims about scheduling.

All measured prompts, statuses, and output token counts matched within the selected paired audits. Some output-text hashes differed even on same-policy repeats; only hashes were retained, so semantic impact is unknown. LMCache's inclusive retrieve spans were observed, but exact H2D transfer and copy/compute overlap were not instrumented.

## Real-data mixed workload (chatbot + document QA)

Measured on 2026-11-22 with 62-request traces: 14 real QuALITY v1.0.1 dev documents (6.0–8.2K tokens, 3 questions each, late revisits) plus 20 real ShareGPT chat prompts. Dataset content is real; arrival times are simulated. The 14 documents total 1.75× the engine-reported GPU KV capacity (98,130 tokens versus 56,160). Two repeats per configuration, SLOs fixed beforehand (chat TTFT ≤ 1 s, doc TTFT ≤ 3 s, TPOT ≤ 100 ms). Details and limitations: [docs/real_workload_results.md](docs/real_workload_results.md).

- **CPU tier (B2 vs B1), burst trace:** B2 restored 94,464 prompt tokens from CPU and computed 102.8K instead of 197.3K (−48%); goodput 2.54 → 4.00 req/s, chat SLO attainment ~0.33 → 0.60, doc ~0.87 → 0.95. Under the moderate trace every configuration met every SLO; the tier only lowered doc p50 TTFT (435 → 166 ms).
- **`max_num_batched_tokens` 2048 → 8192 (B2T vs B2), burst trace:** chat TTFT p95 2.54 → 1.95 s and goodput 4.00 → 4.31 req/s in both repeats, with unchanged summed prefill time; the change appears as lower gateway/engine queueing. vLLM 0.22.0's default on this RTX 3090 is already 2048, so all earlier results used 2048.
- Chat still missed its 1 s target for 30% of burst requests with B2T; no per-class prioritization was tested. Generated text differed between runs even for the same configuration (14–27 of 62 outputs per comparison), and the QuALITY answer letter changed more often under B2T (3–5 of 42) than under B2 (0–1 of 42); accuracy (57–62%) cannot separate configurations.
- Single host, single trace seed, 20 chat requests per run; the comparison is not a general claim.

## Prefill budget, load and queue order (follow-up)

20 runs on the same real-data traces with 60 chat requests per trace and three simulated arrival loads (details, hypotheses and limits in [docs/chunk_study_results.md](docs/chunk_study_results.md)):

- Raising `max_num_batched_tokens` from 2048 to 8192 reduced chat and doc TTFT p95 at every load (burst chat p95 3.43 → 3.02 s, paired CI −488 to −307 ms; light-load gains were small). Under burst the chat TTFT is mostly gateway admission wait; the larger budget shortens first-visit document prefill service time by 10–14% (unchanged for CPU-restored revisits) and the queue drains sooner. The per-step overhead behind this was not measured.
- The cost shows up in the decode tail: the p95 of each chat request's longest inter-token gap rose 2–3× (to ~0.47–0.49 s) with unchanged TPOT, which the TPOT ≤ 100 ms SLO does not detect.
- Admitting chat before queued documents at the gateway cut burst chat p95 from 3.02 to 0.97 s (SLO attainment 0.30 → 0.94) but raised doc p95 from 3.3 to 4.6 s (doc SLO 0.88 → 0.69): under saturation priority moves SLO misses between classes. The CPU tier and the budget effects looked roughly independent in a B1 versus B2 comparison under burst.
- Single host and model, two repeats, simulated arrivals; the budget comparison is chunked versus essentially unchunked for these prompts.

## Queue order below saturation and prefill-step cost (second follow-up)

Is chat-first admission still a trade-off below saturation? At first-visit spacing of 0.5 s it is free: chat SLO attainment rose 0.68 to 0.98 while doc stayed at 1.00 (doc p95 2.58 s). At 0.4 s no policy reaches both targets (FIFO 0.30 / 0.88, chat-first 0.94 / 0.69, chat-first with a 1.5 s age cap 0.53 / 0.85, chat / doc), so that load needs capacity rather than reordering. An isolated, queue-free probe measured about 12 ms per scheduler step (95% CI 10.9 to 13.2): going from `max_num_batched_tokens` 2048 to 8192 shortens a 6 to 8K-token prefill by 22 to 49 ms. The pre-registered age-cap hypothesis (H-b) was not supported; details, limitations and reproduce commands: [docs/policy_study_results.md](docs/policy_study_results.md) (hypotheses: [docs/policy_study_prereg.md](docs/policy_study_prereg.md)).

## Project map

- [Results and caveats](docs/main_results.md), [design decisions](docs/decisions.md), [ideas](docs/ideas.md), [lessons](docs/lessons_learned.md), and [reproduction steps](docs/reproduce.md) are the five living docs; [real-data workload results](docs/real_workload_results.md) is a separate study.
- `src/cacheflow/` contains the gateway, bounded admission scheduler, token-aligned prefix fingerprints, deterministic replay, metrics collector, paired analyzer, quality audit, and plot generators.
- `scripts/` contains stack setup, controlled runs, cache-reset crossover, profiler and audit commands. `results/raw/` holds per-request/metrics traces; `results/figures/` contains paired timelines and the [cache accounting](results/figures/cache_accounting/cache_accounting.png), [capacity](results/figures/capacity/capacity_boundary.png), and [working-set](results/figures/workingset/workingset_pressure.png) plots.
- `results/registry.csv` and individual `.summary.json` files record run IDs, trace hashes, source commits and parameters. Model weights and credentials are excluded from Git.

The baseline commands and host-specific setup are in [docs/reproduce.md](docs/reproduce.md). All performance claims above refer to the recorded single host and workload, with two run-level repeats where stated.
