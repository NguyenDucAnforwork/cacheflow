# CacheFlow V6: research questions and claim boundaries

The main development stage (24 arms,1,440measured requests), native stage (60 arms,2,700requests) and main controls (36 arms,1,260requests) passed complete audits. Full CPU preflight passed all1,986token vectors and three trace identities. Four full mainseed901arms now pass7944/7944requests and R1audits/archives. Oldunion p95regresses23.566%versusbundle; readiness regresses69.198%versusbundle/36.930%versusoldunion despite source/decode/upstream improvements. CapturedchooserCPUold/ready=124.810/323.166s. A separate unactivated epoch-cache prototype has synthetic CPU tests and a queued timing probe, not a speedup or competitive result. Only5/39primary contrasts atonearrival seed are available; nativefirstarm is live. Native48GBpayloadcapacity is observed from its completedwarmup, not a completemeasuredarm. This still does not satisfy the strong-baseline objective. The original questions remain intact: development success, a negative result, a seal or elapsed time does not complete the goal.

Read the [original questions](PROPOSAL_LOCOMO_AGENTPERF_V2.md#2-research-questions-new-scope), [current evidence](V6_DEV_EVIDENCE.md) and [baseline provenance](V3_BASELINES.md). Historical V2/V4/V5 protocols remain separate.

| Question | What current evidence supports | What it does not establish |
| --- | --- | --- |
| **RQ0: redundant prefill and producer readiness** | Fixed-DHAS negatives remain. Native readiness variants repeatedly reach 65,122 new-prefill tokens, matching an independent input-only reference; native/FIFO/old union compute 69,650. A separate vLLM diagnostic reconciles 2.021 GiB of duplicate allocated prefix blocks during pending restore. | The native result is not a vLLM 6.5% claim. The allocation snapshot does not prove tensor contents, completed DMA or the original stall's cause. First text is not a native publication/pinning API. |
| **RQ1: GPU+CPU versus GPU-only, by pressure/reuse/load** | Historical V2 contains matched B1/B2 tiering comparisons under its 1.7B/prompt protocol. V6 main shows policy-dependent CPU-source consumption; native promotion/resource/IO evidence has its own semantics. GPU-fit/low-reuse controls test regime dependence. | All current 4B V6 policy arms have a CPU tier. They do not themselves prove a new 4B causal B1-versus-B2 effect. Do not pool V2 with V6 or infer production throughput capacity from an offered arrival rate. |
| **RQ2: bounded admission versus FIFO/DHAS without tail/low-reuse regressions** | Main pressure development improves tails over FIFO/bundle/DHAS. Native LPM/DFS comparisons retain gains with median/quality costs. Native and main low-reuse pass the declared 5% p95 gate at every seed; main 2-QPS union also improves tails versus FIFO, but readiness adds median costs and mixed tails versus old union. Main GPU-fit shows near-no-op old union versus FIFO, while readiness adds median delay with no observed compute saving. Main abstention and the36-arm audit are complete; full performance/quality/resource evaluation remains pending. Observed ingress bypasses respect the bound of eight. | The strong no-regression interpretation across regimes is unsupported: native 2 QPS has tail regressions, and full mainseed901oldunion/readiness p95regress23.566/69.198%versusthedeclaredbundlebaseline despite beatingFIFO. Union/readiness is a fixed resource/readiness heuristic, not a trained adaptive controller or an implemented latency/queue-cost predictor. Upstream TTFT alone is insufficient. |
| **RQ3: quality, budgets and operational fairness** | Captured outputs, input/source/config/reset/hash/clock ledgers, official scores, cap hits, per-conversation waits and bypasses are retained. The12-question main and native abstention strata score7/12 for every arm/seed, with the same seven correct; answerable F1 is inapplicable. | Equal means or small-stratum accuracy do not prove quality equivalence. Bypass is not an E2E deadline or native liveness guarantee. Manual-abort failures remain. Full FIFO seed901 now has answerableF1=.317162 on1,540QA and category5=223/446=.5; bundleF1=.319006,category5=225/446with163hashdifferences and per-QAscore regressions retained. FullunionF1=.318010/category5=223/446with179hashdifferencesvsFIFO and182vsbundle, including per-QAscore regressions; readinessF1=.315511/category5=223/446with199hashdifferencesvsoldunion and176vsbundle. Remainingnative/repeated-schedule quality remains incomplete. |

## Preserve the type of mechanism evidence

| Evidence | Direct unit and meaning | Unsupported substitution |
| --- | --- | --- |
| Main external-KV consumption | Prompt tokens the vLLM engine labels as consumed from the external tier | Physical bytes, exact DMA duration or every LMCache lookup/read event |
| Native host promotion | Tokens promoted by HiCache load-back in a covered sample window | Main consumption, completed DMA latency or zero when an endpoint is missing |
| Native uncached prefill | Source-labelled newly computed prompt-token count | FLOPs, kernel time, exact per-request redundant intervals or proportional E2E speedup |
| Input-only causal trie | Distinct complete prefix blocks and private tails under full retention/immediate reuse | A scheduler simulator, residency/pinning proof or optimal finite-cache policy |
| Block/refcount snapshots | Allocated physical IDs and logical prefix identities at sampled states | Tensor equality, atomic scheduler/worker join or proven deadlock cause |
| GPU event/kernel diagnostic | Covered operations, payload accounting and temporal intersections in the diagnostic | Unprofiled serving latency, exhaustive copy coverage, pure DMA overlap or useful stall hiding |
| Client TPOT / native histogram | Request-level average-to-close proxy / engine-specific update observations | Exact client token-arrival percentiles or a distribution pooled across engines |
| Gateway stage reconstruction | Per-request additive waits in scheduled-arrival TTFT | Sum of stage p95 values or upstream-to-text interpreted as pure GPU time |

The kernel diagnostic's 9.8% temporal IO/model intersection and measured effective payload bandwidth retain their original phase/model/output/profiler scope. They characterize hardware behavior, not a new causal V6 speedup.

## Hypotheses and falsification

The historical fixed-delay premise was unsupported in its tested vLLM conditions. CPU tiering helps in measured residency regimes, not because CPU memory is intrinsically faster. Readiness can reduce prefill while worsening latency: gate-only FIFO demonstrates this. Lower load can still have tail regressions. Moving queue time outside the backend does not count as improvement; scheduled-arrival timing and stage reconstruction expose that tradeoff.

These are findings about conditions and mechanisms. A positive contribution still needs full serving comparisons, quality/fairness/resource review and practical assessment against the strong baselines. This document does not replace that work with a smaller development-only objective.

## Remaining completion evidence

The remaining work is concrete:

- Main36-arm controls and both-stack low-reuse gates are complete; retain their regressions and small-stratum limits.
- All1,986CPU token vectors/trace identities and prospective source/model/input/config/package seal are complete; these are prerequisites, not serving results.
- Execute and audit the 30 full arms, preserving all measured outcomes, actual host allocations, official quality/category 5, resources and native ITL coverage.
- Review matched within-stack comparisons, regressions and missing coverage; finish reproducible figures/report/interview material and the requirement-by-requirement completion audit.

A reference seal or a test count does not prove those runs succeeded. A final report may support a conditional contribution: portable admission under a declared memory-pressure regime, with measured work/capacity/queue effects and explicit costs. It must not claim full Strata/Cake reproduction, latest-policy SOTA, universal no-regression, quality equivalence, production starvation freedom or a repaired stall without the necessary evidence.
