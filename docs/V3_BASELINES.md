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
