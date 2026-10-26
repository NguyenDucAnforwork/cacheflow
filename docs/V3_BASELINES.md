# V3 baseline applicability matrix

Primary-source literature review, started 2026-10-26. Recency window requested by owner: 2025-04-26 through 2026-10-26. Venue labels below are actual published venues; no numerical speedup is imported as a local result.

| System | Primary publication/code | Relevance and execution status |
| --- | --- | --- |
| Strata | [OSDI 2026](https://www.usenix.org/conference/osdi26/presentation/xie-zhiqiang), [SGLang efficient-I/O PR](https://github.com/sgl-project/sglang/pull/7313) | Directly targets hierarchical KV transfers and cache-aware scheduling. Inspect upstream HiCache implementation; an isolated SGLang baseline is being prepared. HiCache presence alone does not prove every published scheduler feature is enabled. |
| Cake | [ICML 2025](https://proceedings.mlr.press/v267/jin25d.html) | Coordinates prefix computation and storage loading. Main relevance is the cost/overlap model. An ingress-only ordering heuristic cannot reproduce its intra-request compute/load mechanism. Original runnable release must be verified before claiming reproduction. |
| LPC | [NeurIPS 2025](https://proceedings.nips.cc/paper_files/paper/2025/hash/414f642a1ea9350006669774cba9bcd4-Abstract-Conference.html), [original code](https://github.com/yangdsh/LPC) | Predicts continuation for prefix eviction. Original release builds on an older vLLM fork; prediction training and dataset assumptions differ from repeated full-history QA. Assess genuine port/retraining feasibility, not an untrained fake baseline. |
| EpiCache | [ICML 2026](https://proceedings.mlr.press/v306/kim26ag.html), [original code](https://github.com/apple-aiml-research/ml-epicache) | Long-conversation QA and LoCoMo with episodic KV compression. Lossy, changes the cache/quality budget; separate accuracy-memory frontier rather than a direct lossless ordering baseline. |
| vLLM + LMCache | Current pinned upstream implementation | Core serving baseline. Must tune batch/concurrency/graph settings rather than comparing only to a deliberately constrained FIFO configuration. GPU-fit and GPU-only controls remain necessary. |
| Queueing controls | FIFO at multiple caps; longest-prefix-match; shortest-new-prefill; bounded prefix grouping | Simple but strong controls for a proposed gateway method. Same serving process and exact trace can isolate admission/order effects. Specific implementations and parameter tuning will be recorded before confirmation. |

## Environment compatibility evidence

The installed vLLM/LMCache stack remains untouched. Latest SGLang 0.5.22 requires torch 2.14.1 and transformers 5.19.0. SGLang 0.5.14 matches torch 2.11.0 and is being installed into `/venv/sglang-baseline` using shared read-only base packages and isolated package overrides; its declared transformers version is 5.8.1. This version choice and any missing runtime dependencies will be documented. No results yet imply hardware compatibility or successful baseline execution.

## Methodological constraints

A paper's own published throughput on H100/H200 is literature context, not a comparator to our RTX 3090. Every locally measured arm needs matched model revision, exact tokenized prompts, output budget, cache capacity and host-memory budget. Engine-specific allocator and scheduler differences are documented. Profile overhead is excluded from the final unprofiled latency contrasts.

## Compatibility update ~07:22 UTC

The first actual SGLang GPU launch failed at native-library import: PyPI's `sglang-kernel==0.4.4` wheel links CUDA13 cuBLAS, unavailable in the torch2.11/cu128 environment. The official CUDA12.9 index provides `sglang_kernel-0.4.4+cu129-cp310-abi3-manylinux2014_x86_64.whl`, SHA256 `4ea2f7176965c3d1a5697254befe45c2ac995793577108129710d0f66ca85b33`. Its download is progressing through aria2 after uv's direct download made no payload progress; adopt only after complete SHA verification. This compatibility repair is isolated and is not a change to the main serving stack. The native upstream HiCache baseline remains unmeasured until an actual server/replay succeeds.

## First native upstream execution, ~07:44 UTC

SGLang0.5.14 now serves the pinned 1.7B model with native HiRadixCache, kernel/page_first I/O, write-through, 16 GiB host KV and 37,440 GPU KV tokens. A fresh process after isolated runtime pins has decode CUDA graphs (`full`); upstream automatically disables prefill graphs with this Triton attention configuration. Max running requests16, batch8192, seed0. This is an **upstream HiCache/LPM baseline**, not a claim to reproduce every Strata scheduler feature. Actual server config and process arguments are saved per run.

A first 60-QA replay completed but its RSS sampler failed on a transient child-process exit; it is explicitly invalidated for performance comparison. The corrected sampler handles process exits per member. New run `v3-sglang-lpm16-dev3-qps2-s101-r2` succeeds with exact prompt-token agreement and complete native metrics: p50 1.009s, p95 6.939s, p99 7.546s. Seeds102/103 are running. These are dev controls; further backend/concurrency tuning is needed before calling this the strongest supported SGLang configuration on SM86.

**Native counter caveat:** `sglang:load_back_duration_seconds` is measured around `HiRadixCache.load_back`, whose controller queues asynchronous copy work and returns device indices. Its CPU wall duration is not the full H2D DMA duration. `load_back_tokens_total` is the source-labelled host promotion count, not vLLM's engine-consumed external-token counter. Preserve both meanings instead of merging them. Source inspected in the installed `sglang/srt/mem_cache/hiradix_cache.py` and `observability/metrics_collector.py`.

## Paper feature audit and stronger tuning plan (~08:03 UTC)

The [author's publication page](https://zhiqiangxie.com/publications/) links Strata to the HiCache blog; it does not provide a separate full scheduler artifact. Inspection of the installed upstream source supports this narrower mapping:

| Component | Evidence in SGLang0.5.14 | Local baseline interpretation |
| --- | --- | --- |
| Hierarchical radix cache | `HiRadixCache`, host/device match lengths and promotion | Native upstream implementation |
| GPU-assisted transfers | kernel/page_first backend | Native implementation; direct/page_first_direct is a tuning control |
| Layerwise load overlap | `cache_controller.start_loading` uses a separate load stream and records one completion event per layer | Native mechanism; actual overlap still needs a CUDA timeline |
| Cache-aware ordering | native LPM sorts total matched prefix tokens; DFS-weight groups radix subtrees | Strong upstream scheduling controls, not just gateway hints |
| Published balanced-batch/delay-hit/bubble policies | No corresponding full strategy established by the inspected LPM path | Do not label measured LPM as the entire Strata scheduler |

The installed LPM uses both host and GPU match information, whereas gateway `lpm_real` prioritizes observed GPU residency. They are distinct baselines. Native LPM switches to FCFS for queues above128; this matters for larger evaluations and must be recorded. Next tuning controls include direct vs kernel I/O, native FCFS/LPM/DFS-weight, and supported attention backends on SM86, with the same model and memory budget. The exact paper component mapping is based on [Strata](https://www.usenix.org/conference/osdi26/presentation/xie-zhiqiang) and inspected native source; it is not a claim that the complete published policy was reproduced.
