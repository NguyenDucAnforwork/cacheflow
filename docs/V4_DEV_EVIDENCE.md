# V4 development evidence — preliminary, unfrozen

Updated2026-10-26 around10:24UTC. This document separates exploratory evidence from confirmation. No V4 held-out or full1986-QA GPU evaluation exists yet. The active goal is incomplete. Results from V3 and V4 prompts must remain separate.

The current method is external **KV-union admission**: reserve the union of active exact16-token prefix blocks plus per-request suffix/output/safety; admit the oldest feasible request, backfill compatible work while bounding bypass of the head. `packing_reuse` applies packing when a queued prefix group matches active/recent work and otherwise falls back to FIFO. That reuse signal is logical history, not verified KV readiness. The gateway controls order/admission; engine allocator and KV validity remain native.

## RQ2: native baseline and the median–tail tradeoff

Qwen3-4B at pinned revision, BF16,32K context,96-token output, V4 concise/no-thinking prompt; LoCoMo dev conv26/30/41 first20QA each.60 unique questions, seeds101/102/103, exponential4QPS. GPU KV6GiB, CPU16GiB, native LPM16,8192-token chunked prefill, FlashInfer and decode graphs. Three seeds vary serving arrivals, not question diversity. All percentile comparisons count time from scheduled client arrival, including gateway and transport waits.

Kernel/page_first matrix: native LPM, FIFO gateway, packing, packing_reuse, balanced orders.720/720 requests, source-token/output audits pass. Mean p95 native23.062s vs packing_reuse19.207s; p99 24.694→19.902s. **Median6.149→16.838s regresses substantially.** Mean F1 .302831→.307545 is not proof of quality equivalence. Per-seed quality changes include negative values. Native host-promotion aggregate remainsnull because one counter series is missing.

Direct/page_first_direct replication compares native, packing_reuse bypass4 and bypass8, with reversed/permuted orders.540/540 measured requests. Every pair verifies identical trace/prompt hashes, server configuration, backend PID, native source SHA, model/output budgets and complete cache/uncached accounting. The output files are hash-audited and graded with the pinned original evaluator.

| Seed | Native p95 | q4 p95 | q8 p95 | q8 p99 change | q8 p50 change | q8 F1 delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
|101|20.435s|19.332s|18.384s|-13.79%|+216.52%|+0.003 approximately|
|102|23.693s|19.078s|19.047s|-22.36%|+135.21%|-0.005 approximately|
|103|23.566s|19.411s|19.366s|-22.31%|+95.98%|-0.001 approximately|

The q8 p95 changes are-10.03%/-19.61%/-17.82%. Its mean paired F1 delta is-.001066; output-hash differences4/8/8 of60. Do not claim standard-mode bit equivalence. Native-direct has a material median advantage. Concurrency1/4/32, DFS-weight, FCFS and I/O tuning must be considered before choosing a baseline. Initial native cap1 measured seed101 p95=28.733s, slower than cap16. Cap4 still pending at this checkpoint.

![Per-run dev latency tradeoff](../results/v3/sglang/v4_direct_dev_tradeoff.png)

## RQ0/RQ1: transfer and compute evidence

Native SG source counters preserve their meaning: uncached prompt tokens are reported prompt minus cached tokens; host promotions count native loads. They are not automatically equivalent to vLLM's engine-consumed CPU-token accounting. Direct measurement of executed prefill intervals is being added for a separate diagnostic, since counter totals alone cannot explain every scheduling effect.

An instrumented kernel/HiCache candidate run has9 H2D loads,166560tokens and24,560,271,360bytes. Coverage exactly matches its promotion counter. CUDA events on the real load stream, after controller dependency wait and spanning first→last layer, total2.175s, median effective11.29GB/s. Its CPU enqueue timer totals.120s and measures a different stage. The native diagnostic has0 observed load calls, but its absent Prometheus load series staysnull. Neither measurement establishes steady-state overlap with model compute.

A separate batch-invariant vLLM/LMCache diagnostic (V3 prompt, not V4 performance) has0/60 output-hash differences and retrieve-event bytes127,628,476,416→17,477,664,768 (-86.3%). Preserve its scope: batch-invariant kernel mode and event instrumentation are excluded from ordinary latency claims.

The bypass sweep0/4/8/16/32 at configured native in-batch thresholds1024 completes420/420 requests including warm/native. q0 minimizes uncached tokens but has p95=35.959s, versus native20.520s and q8 18.311s. Optimizing a work counter alone is insufficient. Actual maximum head bypass0/4/8/16/19 verifies the guard. Threshold1024 does not reduce native uncached82470 on this seed. Source inspection also rejects an untested explanation: standard admission passes `InitLoadBackParams` without mem_quota, so quota-based restore rejection is not established as the cause.

## Completion gates still open

- Select candidate/config after native concurrency tuning and new V4 low-reuse/GPU-fit/load controls. q4/q8 dev tuning does not freeze either arm.
- Validate telemetry for native prefix/admission/restore events and separate diagnostic overhead from performance.
- Revalidate V4 on main vLLM/LMCache with tuned baselines; V3 prototype results do not stand in for new-policy V4 results.
- Freeze method/config/protocol before GPU evaluation of untouched conv43/44; at least three balanced repetitions for key confirmation claims.
- Evaluate all1986 fit QA. Static prefix hotset is34.031GiB; matched CPU48GiB support is implemented but full GPU serving/evaluation remains pending. Full is a separate memory regime.
- Audit failures, per-category quality, truncation/budget hits, hash differences, queue/fairness and source/config provenance. Finish report and interview explanations after those results.

## Reproduction and artifacts

- `scripts/v4_sglang_direct_replicate.sh`: the nine measured Direct dev runs plus separate warmup; requires existing correctly configured idle gateway and exclusive GPU use.
- `scripts/v4_sglang_guard_probe.sh`: threshold/guard exploratory sweep, unfrozen diagnostic.
- `scripts/v4_sglang_cap_profile.sh`: native cap1/4 screens and opt-in prefix/load diagnostic, latter excluded from normal performance.
- `results/v3/sglang/v4_direct_repl_audit.json`, `v4_direct_repl_quality.json`, `v4_direct_repl_pairs.json`: strict integrity, official scoring and matched pairs.
- `scripts/v4_plot_dev.py`: figure from audited per-run data, visually inspected.
- `results/v3/sglang/v4_guard_probe_audit.json`, `v4_guard_probe_admission_audit.json`, `v4_cuda_transfer_audit.json`; `results/v3/invariant4b_transfer_audit.json`.
- Raw requests/outputs, metrics, server logs and profiler events remain ignored under `results/v3/raw/`; do not delete them. Native upstream files are unmodified; opt-in import hooks and their source hashes are recorded.

For primary paper provenance and exact feature mapping see `V3_BASELINES.md`. Upstream HiCache with native LPM/DFS is a strong measured implementation of several relevant mechanisms; it is **not a reproduction of the complete Strata scheduler**. No published H100/H200 latency is used as a local RTX3090 comparator.

## Follow-up diagnostic,10:29UTC: exact repeated-prefix intervals

`v4_admission_profile_audit.json` joins all60 exact tokenized prompt digests in each diagnostic with native selection events. Scheduled prefill totals match native uncached exactly:82470 native vs75862 q8. Reconstructed same-batch repeated **common-context** token positions total16412 vs9928. Example native batch4: conv30 q000–q003 each schedules the common interval[13280,15188),1908tokens; that is5724 excess context-token computations within that one batch. QA-specific suffixes are excluded from this duplicate measure. Across-batch repeats and alignment effects are separate.

Candidate loads5 times/98288tokens, all successful, mem_quota=None; native has no load calls in the window. This directly rejects a quota-rejected-load account for this diagnostic and supports partial-prefix readiness as an additional testable mechanism. It does not establish GPU kernel durations or steady-state transfer overlap. Instrumented runs remain excluded from ordinary performance claims.

Native in-batch prefix checking only applies below its configured GPU-prefix threshold.32/1024 cannot cover the observed13280-token partial prefix; a prospective32768/1024 native tuning probe is prepared in `scripts/v4_sglang_full_inbatch_probe.sh`, not yet executed. Test that strong control before attributing novelty to external readiness gating. The earlier fixed-DHAS/vLLM negative results remain unchanged.

Current GPU job: `scripts/v4_sglang_controls.sh`, tool12288, Direct native-cap4 replication then V4 low-reuse/QPS2/GPU-fit comparisons, all profilers disabled. Candidate remains unfrozen. Full benchmark and fresh confirmation are still unrun.

Update10:37UTC: native Direct-cap4 replication finished360/360 measured requests. Native/q8 p95 per seed:19.776/17.337,27.063/20.247,26.090/25.578s. Candidate changes-12.34/-25.18/-1.96%; q8 cap4 is variable and slower on average than q8 cap16, so it is not silently substituted as the best method. Mean native cap4 p95 is also higher than cap16 over these dev seeds despite the favorable initial seed101 screen. Audits/quality/pairs are `v4_cap4_repl_*`.

The new q8 admission diagnostic also has independently covered CUDA load events:5loads,98288tokens,14,493,155,328bytes; summed load-stream span1.282s, median11.279GB/s. CPU enqueue sum.01478s is a separate stage. See `v4_admission_cuda_transfer_audit.json`. These measurements remain diagnostic rather than a latency comparison.
