# V8 diagnostic engine-exit amendment

2026-10-27, after the original offA terminal failure. Original V8diag1 remains
failed/incomplete:60warmups succeeded; full offA had423successes/1563errors out
of1986client records, and599.063s sampled nonprogress. Supervisor recorded vLLM
exit0 before replay ended. Its collector required a live unchanged engine at
the end, so failed that check and stopped before on/offB. The original failure,
terminal record and all raw bytes remain unchanged. A separate postmortem audit
checks the entire client/error/output ledger without rewriting that outcome.

V8diag2 executes only the two unexecuted phases,on then offB, in new run IDs.
It never reruns offA or claims original off/on/off completion. Each phase still
gets a fresh engine/LMCache,60separateFIFOwarmups/reset/freshV6gateway and the
whole1986-QA seed902 union64 workload. Original model/config/schedule/resources,
600s client read/pool/upstream timeouts, keepalive0,4native hooks and2s sampling
remain unchanged. No functional upstream patch, V7 epoch policy or retries.

Two explicit changes:

1. After replay only, a missing original vLLM process is a retained failed-engine
   outcome if the full client summary has errors. Successful runs still require
   the same live process; replacements are rejected. LMCache and gateway must
   retain their PID/birth/argv. All client/trace/prompt/token/output and gateway
   coverage checks stay unchanged. Missing final identity is explicitly false,
   never represented as a verified successful bookend.
2. Both phases uniformly tee native stdout/stderr to a private per-phase log
   while preserving supervisor stdout. The wrapper execs the original launcher
   so the supervised engine PID remains the actual vLLM PID. Existing log paths
   reject an automatic restart. This adds diagnostic I/O and cannot support a
   primary latency comparison with the earlier offA phase.

Registration records reversible source transformations of the unchanged
original capture/controller, native/source/model/input hashes, original failure,
postmortem evidence and the exact live CPU-revision parent, or its completed
result plus verified process absence if already terminal. Execution waits for
that CPU job to end, retains its result/failure, then requires all services idle
and GPU memory below1GiB before each new engine. CPU tokenization and inference
must not overlap. Model hashes are checked only while idle.

The remaining-phase controller keeps original cleanup/restore and strict probe
coverage. Warm failure stops it; target errors are retained outcomes. Cleanup
attempts every inference service and restores both original supervisor configs.
All runs receive diagnostic/invalid-for-performance markers before requests and
use a separate registry. No successful-only metrics, quality equivalence, native
root cause or validated-fix claim follows from execution/coverage alone.

The prospective native-HOL prediction was recorded before any profiled journal:
an allocation-blocked head may prevent a later already-finished remote holder
from being promoted. The CPU witness uses installed waiting-loop guards and
promotion/allocation methods with explicit fixture assumptions, not an engine
reproduction. Observations must distinguish that mechanism from pending lookup,
missing remote completion, or all holders genuinely lacking allocation space.
