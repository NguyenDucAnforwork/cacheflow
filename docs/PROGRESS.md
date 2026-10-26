# CacheFlow research progress and server handoff

**V3 active from 2026-10-26 05:59 UTC.** Owner explicitly rejected V2 as a sufficiently strong research contribution and requires at least five additional hours (earliest completion ~10:59 UTC), competitive strong baselines, careful profiling, and `docs/INTERVIEW.md`. Branch `feat/cacheflow-v3-competitive`; read `docs/V3_RESEARCH_PLAN.md` and `docs/V3_BASELINES.md`. V2 values below are preserved baseline history, not a completion claim for the new goal. V2 supervisor programs are currently reused for V3 experiments with an ignored `.cacheflow-v3-runtime.json` marker; inspect health and live handles before starting/stopping anything. Raw V3 artifacts are in `results/v3/raw/`.

## Current V3 checkpoint — 2026-10-26 09:03 UTC

- Branch `feat/cacheflow-v3-competitive`; validated prototype commit `1ab763b` (new variants/profiling follow-up committed as `ab0f90a`). V3 remains **incomplete**; five-hour minimum ends no earlier than10:59UTC, and method/baseline/quality/control requirements remain open.
- Working model4B revision `1cfa9a7208912126459214e8b04321603b3df60c`: all shard SHA verified; V3 concise prompt,96-token cap,6GiB GPU KV,16GiB CPU,maxseq16,batch8192,CUDA graphs. First FIFO dev F1 .3147;1.7B earlier ~.10. This is a60-QA subset, not full LoCoMo.
- Actual KV observer validates live byte-hash namespace, tracks gaps and fails closed. Earlier integer-vs-byte diagnostic runs remain excluded.32 tests pass. CPU decision optimization matches270 prototype selections and exact reservation math; cache invalidates on queue/active/guard and (for LPM/residency) KV-event sequence changes.
- The initial14-arm4B screen completed. Several cap16 grouping arms had HTTP502/ReadError; invalid markers preserve all failures. Never use their successful-only latency percentiles. Post-optimization transport diagnostics both complete60/60 with/without retained connections; socket reuse is not proven as the sole cause. Main runs now use fresh local connections, no retries and stop on request errors.
- Completed15 dev runs900/900, fully audited, from `scripts/v3_replicate_4b_optimized.sh`: FIFO16,LPM16,bundle16,packing16,DHAS16 atQPS4,seeds101/102/103, balanced/permuted arm orders. First seed's completed arms all60/60: p95 FIFO35.472s,LPM33.009s,bundle25.355s,packing24.097s. Mean packing p95/p99 vs FIFO -30.92%/-31.14%, vs bundle -10.51%/-10.67%; p50 +6.02% vs bundle. Low-reuse controls48/48 show zero CPU transfers and mean p95+.91%; GPU-fit control360/360 shows zero CPU transfers and nearly equal p95. See analyses. Current GPU job is invariant/KV-event diagnostic, tool89888; inspect it before switching servers. Candidate remains unfrozen; fresh conv43/44 confirmation untouched.
- Native upstream HiCache/LPM1.7B: three audited runs180/180 success, p95 6.939/8.983/7.761s. It is not the full Strata scheduler. SGLang is stopped. Runtime now supports explicit pinned4B, GPU budgets, kernel/direct I/O, native LPM/FCFS/DFS and attention-backend tuning. Those stronger4B comparisons are still open.
- CPU profiling shows why gateway overhead matters: unprofiled synthetic-size decision old/new-uncached/new-repeated medians12.06/4.57/.0058ms; not E2E speedup. Heavy Torch-profile latency is excluded. Native SGLang load-back CPU timer is an enqueue-path timer, not full DMA time; source counters stay distinct.
- New `packing`/`packing_reuse` variants remove an unnecessary observer-bootstrap dependency; GPU validation is pending. V4 corrects the public evaluator abstention phrase before prospective all-category evaluation; never pool V3/V4. Full V4 gzip trace preparation finished:1,986 QA, no GPU evaluation. FlashInfer0.6.12 Python/cubin isolated install finished and versions match. HiCache4B/FlashInfer serving remains untested; invariant/KV-event GPU diagnostic (tool89888) is still live. Required next: audit/grade dev repetitions, native HiCache4B and backend tuning, low-reuse/GPU-fit and guard ablations, method/config freeze, fresh confirmation and final reproducible report/interview documentation.
- Previous goal turn: **progress** (native baseline, verified4B adoption, GPU measurements, code/docs commits). Current continuation repairs failure handling and CPU scheduling, validates decisions, and runs stronger matched repetitions. Goal stays active.

## Preserved V2 handoff (historical)

Updated: **2026-10-26 05:15 UTC**. Current `optim` host. The owner’s 90-minute continuation produced a measured contribution aligned with RQ1/RQ3 and a cache-metric audit relevant to RQ0. All experiments finished around 05:10 UTC; V2 services are stopped. No credentials are stored here.

## Start here

- Checkout `/workspace/cacheflow-e1`, branch `feat/cacheflow-v2-e1-prep`. `/workspace/cacheflow` is a separate V1 worktree; leave it untouched. V1 results were preserved, with a clearly separate V2 section appended to `docs/main_results.md`.
- Main report: **`docs/V2_E2_RESULTS_2026_10_26.md`**. Frozen protocol/amendments: `docs/V2_E2_PLAN_2026_10_26.md`. Research questions: `docs/PROPOSAL_LOCOMO_AGENTPERF_V2.md`. Environment: `docs/V2_HOST_2026_10_26.md`. E1: `docs/V2_E1_EXECUTION.md`.
- Owner waived M1 old-baseline restoration. Do not restore it as a prerequisite. Do not compare old/new host timings causally.
- **B5 remains gated.** Existing E1 screens show no repeatable avoided prefill from fixed DHAS. No adaptive scheduler was implemented.

## New measured contribution

B1 = GPU prefix cache; B2 = B1 + 16 GiB LMCache CPU L1; both FIFO. Thirty genuine full-history QA per run, 64-token output budget, interleaved exponential arrivals at nominal 0.2 QPS, fresh serving processes, identical tiny warmup and empty-cache reset. Three arrival-seed pairs per condition, middle seed reverses arm order.

| Regime | B2 arrival-TTFT p95 mean change | B1/B2 newly computed prefill tokens | Actual CPU KV tokens B2 |
| --- | ---: | --- | ---: |
| Dev 3 conversations, KV 4 GiB | **-53.86%** | 613,180 / 67,884 | 545,296 |
| Same dev, KV 8 GiB | **+1.79%** | 64,236 / 64,236 | 0 |
| Held-out 2 conversations, KV 4 GiB | **-50.54%** | 323,394–344,450 / 52,482 | 291,968 |

All **540 main-matrix requests succeeded** with exact trace/server prompt-token agreement and no observed preemptions. Dev uses conv-26/30/41, first 10 QA each, seeds 17/29/43. Holdout uses untouched conv-49/50, first 15 QA each, new seeds 101/211/307 frozen before the first B2 dev result. Actual GPU capacities are **37,440/74,896 tokens** at 4/8 GiB. Prefix working sets are 63,688 dev and 47,914 holdout tokens. These deliberately constrained KV budgets establish a residency-regime result, not a claim that CPU tiering is always beneficial on a 24-GiB GPU.

**Measurement finding:** dev B2 reports 2,224 L1 read chunks at both budgets, despite actual external KV being 545,296 at 4 GiB and zero at 8 GiB. L1 read lifecycle events and prefix lookup hits are not engine-consumed CPU tokens. The sampler now preserves source labels and preemptions. Missing counters stay null. A static prompt-only prefix oracle independently matches measured GPU-fit / CPU-backed prefill, including the holdout reference fixed before GPU runs. It is not a runtime simulator or a causal chunk-size ablation.

## Quality and supplemental pilots

- Every main raw-template generation hits 64 tokens; absolute F1 is low. Dev-pressure mean F1 B1/B2 0.073974/0.072746, GPU-fit 0.074773/0.074765, holdout 0.089931/0.087090. Hash mismatches 30/90, 9/90, 46/90 respectively; repeated seeds reuse the same 30 distinct QA per subset. Full generated text is retained privately, and exact per-request official-evaluator scores are tracked. No broad quality-equivalence claim.
- Separate chat-template validation: conv-47/48, first 15 QA each, seed 71, thinking disabled in pinned Qwen chat template, 0.2 QPS, KV 4 GiB. One pair: p95 **9,555.80 → 3,333.80 ms (-65.11%)**, prefill 520,562 → 58,082, 462,480 actual external tokens. F1 **0.113467/0.113390**, budget hits 8/30 and 9/30; 4 hash mismatches. Exploratory and still weak absolute quality; separate prompt protocol.
- Separate P-SESSION dev pair: chronological evidence-visible histories, base 2-QPS arrivals plus 1-second checkpoint gaps, KV 4 GiB. Both arms compute **16,287** tokens and consume **0** external tokens; B2 p95 **+9.21%** in one pilot. No tier work saving in this GPU-fit regime. Full-context QA and checkpoint-adapted scores must remain separate.
- Separate initial two-conversation 2-QPS B1 capacity gate: 30/30 success, p95 6,631.12 ms, substantial queueing. Not a clean low-load comparison.

## Artifacts, validation and process state

- **23 new GPU runs, 690/690 request successes**, zero errors. Registry now totals **34 runs / 751 requests / zero errors**, including the prior 11 runs.
- `results/v2/e2_completion_audit.json` records the final integrity audit. All 11 new matched pairs were validated, including prompt/trace identity, exact server/gateway token counts, output budgets and captured-text hashes, idle reset snapshots and complete token-source accounting. The first dev B1 missing source/preemption samples remain null; its separate post-replay snapshot records zero preemptions.
- `results/v2/e2_runs.csv`, `e2_aggregate.json`, `e2_holdout2_runs.csv`, `e2_holdout2_aggregate.json`; per-seed `*.compare.json`; chat/session comparisons; `e2_quality.json` / `e2_quality_pairs.json`; individual cohort QA audits; `e2_tiering.png` and `.svg`; frozen trace manifests and prefix oracles are tracked. Raw outputs, request logs, gateway rows, full metric samples and server logs remain ignored. **Do not delete raw artifacts before audit.**
- `PYTHONPATH=src /venv/main/bin/python -m pytest -q`: **21/21 passed**. `scripts/v2_preflight.py` passed; changed shell scripts passed syntax checks. Final figure was visually inspected. Analysis dependencies matplotlib 3.10.8 and nltk 3.9.2 were added without replacing serving packages.
- At final audit all `cacheflow_v2_vllm`, `cacheflow_v2_lmcache`, `cacheflow_v2_gateway` supervisor programs were **STOPPED**. Matrix tool session 97139 and follow-on session 20462 completed successfully. No V2 run is waiting to resume. Inspect actual process state before any new start/reset.
- GitHub SSH authentication works in this session. Code/docs/small results are pushed to `origin`, `git@github.com:NguyenDucAnforwork/cacheflow.git`. No token/key contents were copied to docs or logs.

## Reproduce or continue

1. Read the final report and frozen plan. Check `git status --short`, tests and preflight; reuse the working stack. `scripts/v2_prepare_e2.py` regenerates and verifies the six main/holdout traces against tracked manifests. Run IDs reject overwrite; additional repetitions require a new recorded namespace.
2. Prioritize a stronger frozen chat-template QA protocol over additional conversations/seeds, with low-reuse and higher offered-load controls. The current raw-template latency mechanism is sound within scope; absolute answer quality remains an explicit limitation. Keep output capture enabled with `CACHEFLOW_CAPTURE_TEXT=1`.
3. A CPU chunk-size ablation can test the residual-prefill granularity explanation. Interpret consumed source tokens and new compute together; raw cache-hit/read counts alone are insufficient.
4. Revisit scheduling only after a fresh repeatable avoided-work/beneficial-restore opportunity and arrival-latency benefit. Do not infer a B5 gate from the tiering win or the static oracle.
5. `/workspace` is an overlay, not a persistent volume: stop/start preserves it; recycle/destroy does not. Keep code/docs/small summaries pushed. Model weights, official JSON and prompt traces are ignored/reproducible; preserve captured outputs on this instance intentionally.

## Environment and source pins

RTX 3090 24,576 MiB, driver 580.178.04; `/venv/main` Python 3.12.15, torch 2.11.0+cu128, vLLM 0.22.0, LMCache 0.5.3, transformers 5.6.2. Model `Qwen/Qwen3-1.7B`, revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, at `/workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`; original shard byte sizes/SHA verified in `results/v2/adopt_aria_model.log`. No downloader is running.

Official LoCoMo source `data/raw/locomo10.json`, SHA256 `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`. Tokenizer fit: 1,986/1,986 QA fit 32,768 with 64 output tokens reserved; this does not mean all fit concurrently in GPU KV or that the whole benchmark was run. Source/split details: `configs/v2_experiments.yaml`, `docs/V2_DATA_FIT.md`.
