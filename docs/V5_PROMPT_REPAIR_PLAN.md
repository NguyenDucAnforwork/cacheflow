# V5 prospective prompt and measurement repair

Revision1 frozen before any V5 GPU evaluation; revision2 below is frozen before any revision2 GPU evaluation. This is a protocol repair with a fixed admission method, not a newly tuned scheduler or a fresh semantic holdout. The current task remains incomplete until the repaired experiment and final requirement audit succeed.

## Diagnosed V4 defects and preserved evidence

All1986 V4 full prompts contain a system instruction requesting `No information available.` and a user footer requesting `I don't know`. The pinned evaluator only accepts its two prescribed abstention phrases for category5. In the first full native run,155/446 category5 outputs are exactly the legacy response,165 contain it and4 match an official accepted phrase. These are format diagnostics, not a replacement evaluator or a corrected semantic score. Preserve V4 raw outputs, manifests, scores and the original source/configuration seal.

The first native full run is complete1986/1986. The second FIFO64 full run ends1960/1986,26 ReadTimeouts, all inconv30; gateway records17 upstream ReadTimeout and9 client cancellations. It is invalid for complete-success latency comparisons. The V4 sweep is retired after this child becomes terminal; no live request is discarded to improve its result. The decision to repair the conflicting prompt precedes observing the FIFO terminal result. The timeout problem is separate and independently reported.

## Fixed method and explicit compatibility proof

Candidate stays `packing_reuse`, max-inflight64, bypass8, exact16-token causal-prefix union, group minimum1024,96 output tokens and16-token safety page, single CPU preparation worker, fresh local upstream connections and no retries. Scheduler, memory/residency/prefix sources and KV correctness are unchanged from V4. `v5_method_proof.py` verifies every parent-sealed source against the original SHA. Only two files permit exact, enumerated textual patches: configurable read/pool timeouts, client keepalive and their telemetry in gateway/replay. The proof SHA-checks historical source at commita6c118c against the original V4 seal and rejects any additional diff. The V5 seal hashes the resulting source, renderer, plans and input manifests.

Historical timeout defaults remain600s. V5 uniformly uses client read/pool3600s and gateway upstream read3600s; connect/write and maximum concurrent connection limits remain unchanged. Revision2 uses client keepalive0 uniformly; the historical default20 remains available. This permits measuring backlog and scoring every returned output, and does not promise a3600s E2E deadline. Capture actual timeout telemetry in replay summaries and gateway health. The26-error V4 result remains visible; do not portray a longer timeout as a scheduler speedup or a600s SLO success.

## Prompt repair

Use `locomo-qwen-concise-v5`. System and canonical user footer both require `No information available.`. Change only the structural footer, not quotations in conversation or question text. Same conversations, original QA text, order, scheduled offsets, text/captions, model/checkpoint, thinking disabled, maximum context32768, temperature0 and96-token output budget. No gold/evidence/category-specific instruction enters prompts or admission. Exact re-render verifies each parentV4 row before transformation. Every full QA fits; observed token delta is+1. Never pool V4 and V5 latency or quality aggregates.

## Resources and baselines

Qwen3-4B BF16 revision1cfa9a7208912126459214e8b04321603b3df60c,144KiB/token. Dev/repair repeats: GPU6GiB, host payload16000745472bytes (native16decimalGB rounded to16-token pages). GPU-fit dev control10GiB. Full: host payload48002236416bytes (native48GB rounded), GPU6GiB primary and10GiB resource control. Native capacity43680/72816; conservative admission43664/72800. LMCache flags match the native payload byte count exactly.

SGLang0.5.14/FlashInfer0.6.12/Direct/page_first_direct, native maxrunning16, batch8192, graphs, write-through, same-batch delay-hit guard enabled and profiler disabled for every measured arm, in-batch thresholds32/32. This is a Strata-inspired component adaptation, not complete Strata. NativeLPM andDFS are both required. Main vLLM0.22.0/LMCache0.5.3: graphs/native16/batch8192/chunk256, same CPU preparation across arms. Real KV observer uniformly enabled in dev/repair main comparisons involving actual-GPU LPM; full supplemental pureFIFO/bundle/union arms uniformly disable it.

## Actual execution plan and validation

1. Fixed-method validation:39 SG runs1740requests plus18 main runs1080requests, total2820. SG includes native/FIFO/union LPM4QPS, native/union DFS4QPS,2QPS, GPU-fit, low-reuse and a fixed12-QA abstention stratum, all three seeds101/102/103. The stratum is first4 original category5 QA by source index in each dev conversation26/30/41, selected before V5 GPU use; report its small scope. Main hasFIFO16/FIFO64/actualGPU-LPM16/bundle16/fixedDHAS16/union64, three rotated/reversed schedules. No tuning after these fixed configurations run.
2. Protocol-repair repeats:27 runs1080requests, conversations43/44×20QA, seeds701/702/703, same arm graph as V4 confirmation. These conversations were previously exposed under V4; do not call them a newly untouched semantic test set. The algorithm remains the one sealed before their V4 exposure.
3. Full study:17 runs33762requests. NativeLPM/FIFO64/union64/nativeDFS at6GiB across3 seeds901/902/903, native/union10GiB seed901 resource pair, and mainFIFO64/bundle16/union64 seed901 supplement. Full contains previously exposed conversations and is a breadth evaluation. Full gateway maxqueue512; dev/repeats64. All run IDs have a new V5 namespace and reject overwrite.

Require complete success, exact prompt/server tokens and hashes, actual policy/config/source proof, fresh gateway history/decision state and cache reset. Preserve failures; no successful-only performance percentiles. Low-reuse p95 gate remains<=5% regression. Report mean/median/tail, makespan/achieved rate, per-conversation latency, source-labelled compute/promotion/consumed tokens, ingress bypass and every score/hash difference. Do not equate observer/prefix history with allocator ownership or a bypass bound with an E2E deadline.

Run the pinned original evaluator on raw outputs, report answerable F1 and category5 separately with cap hits and per-category paired changes. A repaired phrase does not prove good abstention or quality equivalence. No latest-all-policy or SOTA claim follows from winning these local baselines.

The separate CPU-hot off/GPU-only-profiler/off kernel diagnostic uses the historical V4 context but is not a QA/performance comparison. Its audited kernel interval overlap is separate from the primary Direct backend, whose ordinary memcpy trace has incomplete bulk-copy coverage. Full latency measurements remain unprofiled.


## Revision2: prospective fresh-client transport control

Revision1 validation stops on one local `ReadError` after6.536ms in FIFO seed102, before that request appears in the gateway log. Four measured arms complete240/240; the fifth has59/60. All raw artifacts remain and no successful-only comparison or request stitching is allowed. This is distinct from V4 full26ReadTimeouts. Exact socket cause is unproven; disabling client socket reuse is a mitigation/control to validate, not a proven causal repair.

Archive the original seal/plan as `v5_prompt_freeze_v1.json` / `V5_PROMPT_REPAIR_PLAN_v1.md`, with all11 original sealed source files preserved byte-for-byte under `results/v3/protocol_sources/v5_r1/`. Revision2 restarts the complete validation/repeat/full graph with `v5r2-*` IDs, client keepalive0 for native and gateway arms alike, maximum concurrent client connections256 unchanged. Replay summary records the actual keepalive setting. Prompt inputs and all21 manifests are unchanged. Candidate, preparation, CPU/GPU budgets, native guard, bypass and output cap are unchanged. Revision1 results are diagnostic and never pooled with revision2.

A new seal, source verification, tests and fresh serving process precede revision2 GPU use. A later failure stops the pipeline for diagnosis; it does not authorize hidden retries. Full source/quality/latency requirements remain open.
