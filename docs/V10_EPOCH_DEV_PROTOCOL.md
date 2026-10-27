# V10: prospective GPU evaluation of mutation-epoch scheduling

Written 2026-10-27, before any V10 GPU request. This explicitly replaces the
unexecuted V7 development attempt with a new namespace and prerequisite gate.
Original V7 requires a successful original30-arm full study, which failed; its
sources, failure and unmet gate remain unchanged. V10 does not complete V7/V6.

## Question and scope

Does caching unchanged scheduler state until a mutation/deadline reduce actual
CPU scheduling cost and end-to-end arrival TTFT under GPU/CPU-KV pressure? Does
that reduction make the union policy competitive with main bundle16 and native
SGLang DFS? The pure selection policy and resource reservations stay unchanged.
CPU45-case timings and real-prefix ledger parity motivate this measurement;
neither is an E2E speedup or exact production decision-trace proof.

V9 is a separate native bookkeeping diagnostic. Every main V10 arm, including
bundle16 and original union64, receives the same one-statement idempotent lookup
correction. Thus an epoch contrast cannot take credit for the native correction.
Native SGLang does not use that LMCache connector. All timings are unprofiled:
no V8 native observer, no GPU profiler, no per-call identity instrumentation.
Constructor fingerprints, PID/birth and unchanged proof files bracket main
requests; these are startup identity plus continuity, not repeated live-code RPCs.

## Required evidence before freeze/start

- Exact registered live V9repair2 controller has terminated; serving is idle.
- `v9repair2_audit.json` independently reopens all six complete diagnostic arms,
  official quality, raw ledgers and source/code identity. Require six fresh engine
  and CPU-cache units,8064targets/360warmups, zero request errors in both probe
  arms, positive sampled reference inflation and zero sampled candidate inflation.
  Both full901/902 whole outcomes must exist. Full errors are retained, with
  quality/work comparisons absent for failed pairs. Diagnostic integrity does
  not require a successful full workload: the one-site correction was never a
  proposed liveness repair. V10 stops on any error in its own dev workloads. No quality
  equivalence, liveness fix or latency benefit is inferred from this gate.
- Original full checkpoint10 and its failed union902 workload remain bound,
  explicitly10complete/1failed/19unexecuted, not30completed. The failed whole
  workload is not converted into a successful-only latency table.
- Actual from-official-source1986QA regeneration, eight-file namespace proof,
  all45CPU cases and revised V8 real-prefix3972trajectory/4966point parity pass.
  Missing internal wakeup/head/lock history stays explicit.
- Source/protocol/native/evaluator/model/input/package hashes match. The serial
  registration pins existing proof bytes and all V10 code before execution;
  freeze additionally pins the newly completed V9 terminal audit.

## Fixed matrix

`v10_epoch_plan.build_plan()` is authoritative:18fresh-engine arms,60targets plus
60separate FIFO warmups each;1080targets+1080warmups,60already-exposed answerable
QA, three arrival schedules101/102/103. These QA contain no category5. Full1540
answerable+446category5 confirmation remains necessary.

Per seed: main bundle16/reference-union64/epoch-union64; native DFS/reference-
union64/epoch-union64. Seed101 uses listed order,102 reverses it,103 swaps engine
blocks. Native union uses LPM engine policy with the existing same-batch guard;
DFS is a mandatory stronger reference. This is not a full Strata replication.

Pinned Qwen3-4B/V5 prompts,96output tokens, nominal4QPS,6GiBGPUKV,16native
sequences,8192batch tokens,CUDAgraphs. Configured CPU payload16000745472bytes;
main lazy heap16039018496bytes and native payload16000745472bytes are audited
separately, not exact cross-engine heap/RSS equality. Queue512,bypass8,threaded
preparation. Uniform180s client read/pool and upstream timeouts,keepalive0.
Fresh engine/CPUcache per arm,60FIFOwarm, cache reset and fresh zero-state gateway
before measured replay; warmups are not included in performance summaries.

## Audit and interpretation

Retain all18outcomes; stop on first warmup/request/identity/audit failure, clean
all serving services and restore both supervisor configs and implementation
marker. No implicit retries, output stitching or dropping failures. Per-run
checks cover source/runtime configuration, actual gateway reference/epoch class,
main native effective-code identity, prompts/tokens/outputs/clocks, CPU capacity,
source-token reconciliation, native ITL coverage, waits and fairness. Audit and
archive before the next arm; terminal audit reopens all18lossless archives,
recalculates official scores and requires18engine/9LMCache process units.

Twelve primary same-engine/seed contrasts compare epoch with originalunion and
strongbundle/DFS; six supplemental pairs compare originalunion with each strong
baseline. Report every median/p95/p99/completion/fairness/quality regression,
output-hash changes, source work and scheduler CPU/calls/cache hits. Three
arrival schedules repeat fixed QA; intervals are exploratory, not independent
semantic replication or quality-equivalence evidence. No cross-engine causal
latency pooling or backend unique-byte/DMA claim from consumed token counters.

A small-dev timing loss is evidence, not automatic falsification of a large-
queue CPU hypothesis. Before a competitive contribution claim, prospectively
run matched low-reuse/GPU-fit/load controls and full1986QA three-seed comparisons
against bundle/DFS, with all errors and category5. Freeze any further policy
change separately before its measurements. Finish reproducible report and
Vietnamese INTERVIEW and audit the original research objective; this stage
alone cannot complete it.
