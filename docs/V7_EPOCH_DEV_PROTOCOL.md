# V7 epoch-cache development protocol

This protocol is prospective. Only an actual matching seal permits execution.
That seal records this file's exact SHA before the first GPU request.
The original V6 full30-arm study remains unchanged and must complete first.

## Objective and scope

Test whether mutation-epoch cache keys/deadlines reduce real serving CPU cost
without changing the existing pure union selector/reservations/bypass rule on the
same logical state, and whether this yields useful E2E behavior before strong
main bundle and native DFS baselines. Keep latency/quality/median/conversation
regressions. CPU speed alone is not a competitive research contribution.

This is an integration/development screen on60already-exposedQA and three arrival
schedules, not fresh semantic confirmation or a substitute for the full1986QA
large-queue scaling test. A neutral small-workload timing result cannot refute
the large-queue hypothesis. Controls and new full confirmation remain required
before a strong claim; errors/material regressions must be investigated first.

## Required existing evidence

Before freezing or launching, require actual successful artifacts for the
original30-arm R1 full audit(59,580measured/1,800warmup/39pairs), official-source
input regeneration(1,986QA/three exact traces), R1 namespace preparation(30fresh
planned arms, no serving reproduction claim),45-case CPU probe and two-history
real-prefix checker(3,972trajectories). Verify their registration/result hash
lineage and unchanged pinned sources. Missing, partial, failed or changed proofs
stop the pipeline. Tests/plans do not stand in for these results. Preserve the
checker caveat that original lock/head/wakeup histories were not captured.

Freeze code/protocol/inputs/packages/model/prerequisite identities while all
serving services are idle. Verify original model weights outside measurement.
Reject any reused run ID, existing execution record, implementation marker or
unexpected supervisor entrypoint. No parallel engine or retries.

## Fixed graph

`v7_epoch_plan.build_plan()` is authoritative:18fresh-engine arms,1,080measured
requests and1,080separatewarmups. Each seed101/102/103 includes:

| Engine | Strong baseline | Existing method | Candidate |
| --- | --- | --- | --- |
| Main vLLM/LMCache | Bundle, cap16, reference | Union, cap64, reference | Union, cap64, epoch |
| Native SGLang/HiCache | Direct DFS-weight | Gateway union, cap64, reference | Gateway union, cap64, epoch |

Seed101 uses the listed main block then native block. Seed102 reverses all six
arms;103 swaps the engine blocks. Every measured arm gets a fresh engine and,
on main, fresh LMCache. All have the same pinned Qwen3-4B/V5 prompt/output96,
6GiBGPU KV,16,000,745,472configuredhostpayloadbytes,native concurrency16,batch8192,
queue512,bypass8,thread preparation,4QPS scheduled arrivals and180second uniform
read/pool/upstream timeouts with keepalive0. Main observed lazy heap must be
16,039,018,496bytes; native observed capacity must map to16,000,745,472payloadbytes.
This is not exact allocator/RSS equality or causal cross-engine timing.
Gateway prefix blocks256,min-shared1024tokens,max-wait200ms,store-grace20ms and
group-window30ms remain fixed. Freeze validates all three schedule labels,
canonical digests and equal non-arrival prompt/QA/token semantics.

Native retains FlashInfer, Direct I/O, page16, write-through, same-batch delay-hit
component and existing CUDA graph settings; it is not complete Strata. Native
direct DFS and gateway union differ in admission/preparation/transport together.
Main bundle/union differ in configured cap as declared; neither strong-baseline
contrast is an ordering-only causal ablation. Reference union versus epoch union
is the intended same-policy optimization contrast with matched resource settings.

For each arm run60FIFO main or direct-native warmup requests on seed101, then
reset cache and use a fresh gateway before measurement. Warmup uses reference
implementation. Native warmup retains that arm's engine scheduler. Warm and
measured engine/cache process IDs must match within an arm; measured engines and
main caches must be distinct across all18arms. Warmup requests never join latency
or quality totals for measured results.

## Implementation proof

Only the explicit V7 factory may instantiate the new classes. Its separate
implementation marker is `reference` or `epoch`; forbid switching modes inside
one process. Preserve the original selector function object and semantic policy
name. Capture constructor class/selector/startup source SHA from `/implementation`,
actual factory argv/public implementation/PID/birth and idle/fresh health before
replay. Capture the same identity after response completion. Verify both identity
boundaries strictly bracket the actual client request ledger. The factory hashes
source at construction, not retrospectively after code changes.

Main wraps unchanged request/output/metric capture. Native collector changes
only explicit implementation arguments, V7 identity/source metadata and factory
checks, with source transformation proof. The development configuration contract
derives from the original full contract by explicit dev count/host/timeout/factory
substitutions and the R1 last-value scalar parser correction. No old invalid
marker exemption is inherited.

## Execution, failures and independent audit

Stop on the first failed warmup, measured replay, audit or archive. Preserve
failure/invalid metadata and all raw data; never produce successful-only failed
run quantiles or silently retry. Stop every owned serving service on cleanup,
attempt remaining stops even when one fails, restore supervisor configuration and
remove the temporary implementation marker. Never stop management services.

Audit before archival: exact trace/prompt/token/model/source/output identities,
all60successes/zeroerrors, output hashes/budgets, actual configurations and transport,
warmup separation, implementation boundaries, source accounting, native histogram
coverage, observed host capacity, official quality, waits, fairness and resources.
Archive losslessly only after complete audit and stopped writers. Terminal audit
opens all18archives and recomputes every per-run check before pair aggregation.

Preserve missing counters as null. Native promotion/enqueue duration is not DMA;
chooser CPU excludes timeout/condition/tokenization/HTTP and is not recoverable
wall time. Histogram bucket bounds are not exact client-token ITL quantiles.
Stage means add; stage quantiles do not. Keep per-conversation waits and actual
bypasses; a bypass bound is not an E2E deadline or production-liveness proof.

## Analysis and subsequent work

For each engine/seed, primary pairs are reference-union→epoch-union and strong
baseline→epoch-union(12pairs). Keep strongbaseline→reference-union separately as
six baseline-strength diagnostics. Verify matching prompt/trace/model/resource
identities and fresh process units. Preserve all three schedule repetitions and
all per-question output/official-score/cap changes, along with TTFT/completion,
decode, source work, CPU/resources and per-conversation regressions. Similar means
do not prove equivalent quality. n3log-ratio t intervals are exploratory with
unverified assumptions, not1986independent system repetitions.

A complete development audit is not research completion. Register and measure
matched low-reuse/GPU-fit/load/abstention controls and a new full large-queue
confirmation before any strong contribution claim. Preserve V6 main bundle
regressions and native median/conversation penalties. If a candidate fails, keep
the evidence and continue profiling toward the original research objective.
