# V6 native validation protocol

Prepared 2026-10-26 18:04 UTC, before any `v6native1` GPU execution. This is development validation, not a final-method freeze or fresh semantic holdout. The completed V6 pilot does not establish that readiness improves on original union admission or fixes the historical stall.

`PYTHONPATH=src /venv/main/bin/python scripts/v6_native_matrix.py --plan` prints the execution graph without modifying services or runtime files. Execution registers all actions, trace/source hashes, native package/source pins and original supervisor configuration before GPU use. Run IDs cannot overwrite an existing registration/setup. The launcher requires the completed 24-arm main audit and idle serving services. `v6_after_main_native.py` verifies the live main and analysis process identities, waits for both to terminate, and executes the native controller once. Missing/failed main audit stops it; it never restarts the main job.

| Regime | GPU KV | Native scheduler | Arms per arrival seed | Requests per arm |
| --- | --- | --- | --- | --- |
| Primary, 4 QPS | 6 GiB | LPM | native, FIFO64, old union64, readiness-only FIFO64, readiness+union64 | 60 |
| Scheduler control, 4 QPS | 6 GiB | DFS-weight | native, readiness+union64 | 60 |
| Lower load, 2 QPS | 6 GiB | LPM | native, readiness+union64 | 60 |
| Low reuse, 4 QPS | 6 GiB | LPM | native, readiness+union64 | 8 |
| Development GPU fit, 4 QPS | 10 GiB | LPM | native, readiness+union64 | 60 |
| Abstention stratum, 4 QPS | 6 GiB | LPM | native, readiness+union64 | 12 |

Three arrival seeds 101/102/103 give 45 measured arms and 2,100 measured requests. These reuse exposed QA; counting repetitions does not create independent semantic examples. Each regime/seed block starts a fresh SGLang process and receives the same 60-QA native warmup: 18 blocks and 1,080 separate warmup requests. Primary order is normal/reversed/rotated; two-arm blocks reverse the middle seed. This is an order permutation, not perfect counterbalancing of all positions with only three seeds.

Within a block, paired arms share the native engine, with native cache flush before every arm and fresh gateway state for gateway arms. Across blocks, native engines are distinct. This differs from the main V6 matrix's fresh engine per arm: report these protocols separately. An arm failure stops this study, retains raw outputs/invalid status, and does not trigger retries or successful-only latency tables. Fresh engines do not establish production liveness; the original manual-abort failure remains part of the record.

All native arms use pinned Qwen3-4B, BF16, 96 output tokens, FlashInfer, Direct HiCache, graphs, max-running 16, batch tokens 8192, host flag 16 decimal GB, thresholds 32/32, and the same-batch delay-hit component guard. This is a component adaptation, not full Strata. Gateway arms use one preparation worker, cap/queue 64, bypass 8, logical KV admission budget 43,664 or 72,800 tokens, and no residency event subscriber. Client read/pool and gateway upstream timeouts are uniformly 180 seconds, keepalive zero. No GPU profiler or liveness probe is enabled. Within-engine resource matching does not establish cross-engine actual heap equality.

The V6 native collector uses `cacheflow.v6_replay` and captures the actual V6 gateway factory argv, its source hashes, native argv/config/environment/package/source pins and fresh-state evidence. Original V5 collectors and actors stay byte-identical. Warmup status is an explicit CLI flag. A counter absent at either endpoint remains null: the initial warmup can lack a cached-token counter, whereas measured runs require complete cached+uncached prompt decomposition. No missing counter is silently converted to zero.

Two passive native metrics GETs bracket each replay, outside the request window. Histogram acceptance requires matching nonzero engine PID, complete prompt/generation-token coverage, finite counters, unchanged bucket schema, nonnegative monotonic bucket deltas, and +Inf equal to observation count. Coverage failures produce null native mean/bounds; they do not invalidate an otherwise complete request ledger. SGLang's histogram weights averaged update intervals by emitted-token count; it does not record exact client token arrivals. Quantiles are bucket bounds, and client TPOT remains a separate request-level proxy.

`v6_audit_native_matrix.py` requires all 45 measured arms and 18 warmups, restores/checks supervisor config, verifies process-block identities, fingerprints, prompts, reset states, budgets/transport, token accounting, native histogram coverage and official evaluator output hashes. It writes official quality, matched prompt/hash/latency/F1 deltas and completion/decode evidence. Category-5-only answerable F1 remains null. No quality equivalence follows from nearby scores. Native validation cannot replace main-stack controls, a prospective final-method freeze, the full 1,986-QA evaluation, fairness/resource analysis or the final research requirement audit.
