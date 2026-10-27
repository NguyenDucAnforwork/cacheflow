# V8: full-workload liveness diagnostic

Prospective protocol, 2026-10-27. This is separate from the immutable V6 full
study and the gated V7 CPU/epoch study. It cannot complete either study.

## Trigger and question

The original full union seed902 attempt terminated naturally at02:46:42UTC:
1986client records,973successes,1013errors. Its original3600s timeouts, raw
summary, outputs, invalid marker and continuation interruption remain intact.
`v6full1_union_s902_terminal_failure.json` checks every client record against
sealed fingerprints and records3597.813s of exact no-progress metrics.
No successful-only percentile or final healthy CPU-server status proves the
native failure mechanism.

The question is whether a new occurrence is associated with native allocation
failure, unresolved lookup, or absent remote-load completion. Two CPU witnesses
motivate fields to observe; neither establishes engine-state reachability:

* Two requests can logically reserve158pages within160, but if their1024-token
  common prefixes occupy separate64-page copies, only32free pages remain and
  both40-page suffix allocations fail. Shared physical-prefix control succeeds.
* Re-reading one1024-token cached lookup2/8times before allocation succeeds
  increases the installed tracker's stored watermark to2048/8192 and suppresses
  a later otherwise-eligible512-token STORE. An unactivated one-site max update
  fixes the CPU metadata fixture; it is not a serving fix or the stall cause.

## Fixed actions and isolation

`scripts/v8_full_liveness_diagnostic.py plan` defines exactly three phases:
offA,on,offB. Each phase uses a fresh vLLM process and LMCache server, runs the
same60development FIFO warmup, restarts the V6 gateway and resets cache, then
replays the complete original1986-QA seed902 input under packing_reuse/cap64.
There are5958target requests and180separate warmups planned. No history from
another phase is reused, no request retry, no native functional patch, no V7
epoch policy. The probe runs only in the middle phase, including its warmup.

Pinned Qwen3-4B revision1cfa9a7208912126459214e8b04321603b3df60c, BF16,
6GiB GPU KV,48002236416configured CPU bytes, maxseq16,batch8192,CUDA graphs,
queue512,bypass8,threaded preparation,96output cap, original arrival schedule.
Main heap rounding may yield48049946624bytes; this is not RSS equality.
All three phases use600s client read/pool and gateway upstream-read timeouts,
keepalive0. This explicitly differs from the original3600s protocol. A600s
timeout can truncate a healthy long request, so diagnostic failure counts and
off/on/off differences do not themselves prove deadlock or a performance gain.

Registration pins scripts, native source, model artifacts, protocol, input bytes
and original supervisor configs. Execution waits for the exact registered last
V7 waiter (or verifies all workers already terminal by process scan), checks its retained prerequisite failure and terminal result/failure
markers of every earlier CPU worker, then requires all inference services idle.
Model hashes are checked only while idle before each fresh engine. Original
study sources, gates and failure results remain unchanged. No second engine.

## Observation contract

Fresh-process import hooks wrap Scheduler.schedule, KVCacheManager.allocate_slots,
LMCacheMPConnector.build_connector_meta and LMCacheMPWorkerAdapter.get_finished.
They call the original method once, preserve its result/exception and sample
metadata after it returns at most once per2s per target. Allocation failures
record requested new/external tokens, held blocks and free blocks. Scheduler
snapshots retain waiting status, computed tokens, existing block tables/refcounts,
expected-prefix duplicates, lookup membership and received-finish IDs. Connector
snapshots retain operation ranges and stored/scheduled watermarks. Worker
snapshots retain future/event memberships and the original returned finish sets.

No added future.query/result, CUDA event query/synchronize, tensor inspection,
debugger attach, get_blocks side-effecting table lookup or kernel profiler.
Hooks add CPU/I/O overhead and can change scheduling. Across-process snapshots
are not atomic. Expected hashes identify expected prefix geometry, not actual
tensor equality or completed DMA. Any observation failure is recorded separately;
native results are unchanged. Coverage requires all four hook-ready identities,
matching actual native source SHA, scheduler/connector/worker samples, and no
probe_error. Allocation failure is an observation, not a mandatory outcome.

## Evidence and terminal behavior

`v8_diagnostic_capture.py` calls the unchanged V6 replay with a separate registry.
Every run receives an invalid-for-performance marker before requests. Full
client records and partial/empty outputs are mandatory even with errors. Missing
gateway closed records are explicitly counted: pool-timeout requests may never
reach ingress. Client IDs/prompts/token counts/output hashes, serving PID/birth,
config and source identity are checked. This integrity check is not an official
quality or full token-source audit. Original raw replay summaries may contain
successful-only percentiles; they are private retained bytes and excluded from
diagnostic reports. No diagnostic run is admitted to a primary comparison.

A warmup failure or capture/integrity failure stops this diagnostic, retaining
its error. Expected target request failures remain outcomes; the next fixed
phase runs fresh without retrying the failed phase. Every cleanup attempts all
inference services, restores both original supervisor configs and reloads them;
cleanup failures are retained. No original evidence is overwritten or archived
under a misleading successful full-audit contract.

After the diagnostic: inspect native states and probe perturbation before
claiming a mechanism; if not reproduced, report that result and do not claim a
fix. Any functional mitigation requires a separate prospective protocol, native
correctness/quality checks and unprofiled full/strong-baseline evaluation.
