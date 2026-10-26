# V3 baseline applicability matrix

> **Measurement correction,15:38UTC:** LMCache default lazy allocator rounds its heap to64MiB. Configured-byte flags match native payload, but actual cross-engine heap parity is not established: current main repeat reports16039018496bytes vs native16000745472bytes (+.2392%). Full main48049946624bytes is a source-derived prediction vs native48002236416 (+.0994%), not yet observed. Within-engine policy arms remain matched; do not make causal cross-engine timing comparisons. See `results/v3/v5_host_allocator_rounding.json`. The sealed plan is preserved with this external correction. The stalled main repeat was manually aborted; no full study has started.

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

## Current source/measurement boundary,10:47UTC

Native SGLang0.5.14/FlashInfer/HiCache4B is now measured on V4 LoCoMo dev with three-seed kernel and Direct crossovers, actual graph/IO/cache configuration and source hashes per run. See `V4_DEV_EVIDENCE.md`; native concurrency1/4/16/32 and LPM/FCFS/DFS have been screened, with limitations of single-seed tuning recorded. Candidate tail gains have a substantial median cost, and some control runs were invalidated for retained gateway state. Neither a universal win nor a full Strata reproduction is established.

A fresh [upstream source audit at commit c25c24d](https://github.com/sgl-project/sglang/blob/c25c24d78322a623293ae3c097270b1316af0bcc/python/sglang/srt/managers/schedule_policy.py) still finds a default32 in-batch prefix-check threshold. The newer source also has HRRN/token-aging and shortest-prefill-first (including chunk reservation) plus other structural changes. They are **not executed** by this pinned0.5.14 baseline; copying only an ordering function would not reproduce the full newer policy. Source SHA/provenance is retained in `results/v3/sglang/current_upstream_policy_source.json`. Do not generalize results to every latest SGLang policy or describe the partial-prefix issue as a verified bug in all releases. The next local control tests full-context threshold32768 before considering extra readiness logic.

### Same-batch component adaptation,11:19UTC

An opt-in guard inspired by Strata4.3.1 is now executed on native HiCache4B/Direct/LPM16. It compares exact missing-prefix intervals against already selected requests, defers >100 matching compute tokens and lets native scanning consider complementary requests. Original installed files remain unchanged; process env and overlay source SHA are captured. This is explicitly **same-batch delay-hit guard only**, not full Strata, not complete inter-batch transient-node tracking, and no balanced-batch/bubble implementation. Three measured pilot arms total180/180: native17.262s, FIFO64-worker18.083s, union64-worker16.049s p95. Union has a large median cost; results are single-seed and unfrozen. See `v4_guard_component_pilot_*` and `V4_DEV_EVIDENCE.md`.

## Validated baseline status,12:59UTC

The isolated0.5.14 environment now serves4B with FlashInfer0.6.12.33 guarded Direct development runs complete1668/1668 requests, with nativeLPM, gatewayFIFO64, union64 and nativeDFS comparisons plus lower-load/low-reuse/GPU-fit controls. Same-batch guard is uniformly enabled within these comparisons; no profiler is enabled. Main vLLM/LMCache adds18 clean dev runs1080/1080 requests spanningFIFO16/64, actual-GPU LPM16, bundle16, fixedDHAS16 and union64. Detailed tradeoffs and source-labelled counters are in `V4_DEV_EVIDENCE.md`; near-equal quality means are not a quality-equivalence proof.

Native HiCache memory flags in earlier sections were incorrectly labelledGiB: they are decimalGB with page rounding. Prospective held-out/full arms now match exact host payload bytes to LMCache, while historical within-stack dev contrasts remain unchanged. Frozen full primary comparisons include nativeDFS at every seed because LPM's >128 queue fallback can otherwise weaken a large-queue baseline. Latest HRRN/SPF and the complete Strata scheduler remain unexecuted; do not claim dominance over them.

Primary publication pages rechecked2026-10-26: [Strata, OSDI2026](https://www.usenix.org/conference/osdi26/presentation/xie-zhiqiang) describes GPU-assisted transfer plus delay-hit, balanced-batch and complementary-work policies. [Cake, ICML2025](https://proceedings.mlr.press/v267/jin25d.html) jointly schedules computation and loading; neither ingress union admission nor the local same-batch guard reproduces that intra-request mechanism. These papers motivate the experiment, while local numbers come only from the recorded runs. The [efficient-I/O PR7313](https://github.com/sgl-project/sglang/pull/7313) is a provenance link for upstream transfer work, not evidence that all published Strata policies are active.


## V5 repaired-protocol baseline validation,15:29UTC

All57V5 validation runs2820/2820success pass source/budget/transport/output/quality contracts. This comprises39nativeSG1740requests and18main1080requests, with16000745472byte configured-flag parity; actual LMCache lazy heap rounds higher as corrected above. Main actualGPU-LPM/bundle/fixedDHAS/FIFO and nativeLPM/DFS+same-batch guard are executed on the repaired prompt. Sources, conditions, negative controls and decode penalties appear in `main_results.md` and `V4_DEV_EVIDENCE.md`. All18nativeSG repair-repeat runs720/720 and first3main runs120/120 are complete at this checkpoint; the27-run stage audit and full study are still pending. Recent-paper component boundaries above remain unchanged: no completeStrata/Cake reproduction, noHRRN/SPF execution and no cross-stack pooling of cache-counter/ITL semantics. The strong-baseline requirement is not satisfied merely by a dev table; full comparisons and final quality/fairness review remain required.

## V6 audited main and native primary subset,19:06UTC

The fresh-process main matrix completes24arms1440/1440measured requests0errors, withFIFO16/64,actualGPU-LPM,bundle,fixedDHAS,oldunion,gate-onlyFIFO and readiness+union. The native primary subset completes15arms900/900requests0errors across3fresh guardedDirect/LPM blocks: native,FIFO64,oldunion,gate-onlyFIFO,readiness+union. Expanded nativeDFS/lowerload/lowreuse/GPUfit/abstention controls remain live within the60-arm stage; full30arms have not started.

Native readiness+union p95 versus nativeLPM changes−13.696/−26.484/−21.687%, with large median costs and lowerF1; versusoldunion−2.199/−5.662/−4.294%, exploratory interval crossing0. Bothgatevariants reduce observed native new-prefill69650→65122 atall3seeds, matching an independently tokenized input-only page16reference; gate-onlyFIFO still worsens p95atall3seeds. `V6_DEV_EVIDENCE.md` retains quality, missing promotion-counter endpoints, process scopes, oracle/native-tokenizer parity and negative results. These local numbers do not establish completeStrata/Cake reproduction, latestHRRN/SPF dominance or quality equivalence. Fullcomparisons remain required.
