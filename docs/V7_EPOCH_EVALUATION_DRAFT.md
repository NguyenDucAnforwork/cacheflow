# V7 epoch-cache evaluation: prepared, not frozen or executed

This document describes the next experiment, not a completed contribution or a
replacement for the running V6 full study. No V7 GPU controller is registered or
running. The original30-arm study and its source/configuration seal remain intact.

## Question and falsifiable hypothesis

RQ2 asks whether admission remains useful once all frontend costs count. Full
main oldunion/readiness spend124.810/323.166thread-CPU seconds in the chooser;
native oldunion spends50.257seconds. Stable-result hit fractions exceed99%, but
the current key rebuild still traverses lifecycle containers. Replacing that key
and repeated deadline scans with mutation epochs may reduce CPU cost while
preserving the selector, reservations and bypass rule on the same logical state.

This does not predict a proportional E2E improvement. Client arrival limits,
GPU/I/O overlap, condition wakeups and batching can dominate; the native full
oldunion already finishes close to the end of the arrival stream. Logical state
equivalence does not promise identical wall-time dispatch or generated text.
The hypothesis fails as a serving improvement if CPU savings do not translate
into useful latency/resource outcomes before strong baselines, or if operational
or quality costs outweigh them. A faster CPU loop alone does not finish the goal.

## Preconditions before any V7 GPU request

1. Require the actual original full30-arm R1 audit:59,580measured successes,
   1,800separatewarmups,39registered comparisons, preserved failures/amendments.
2. Require completed from-official-source1986QA/three-trace regeneration and
   actual R1 namespace preparation. A generated plan is not independent serving.
3. Require the registered45-case CPU probe and the registered real-prefix checker
   to finish successfully. Keep every sample and every diagnostic disagreement.
   The latter always states that missing lock/head/wakeup history prevents exact
   production decision replay. Do not replace either missing result with tests.
4. Validate source/package/model/input identities and idle services; do not run a
   second engine. Then create a new prospective registration/freeze binding the
   finalized controller, collector, audit, source, protocol and input files.
5. The executable GPU controller and independent request/configuration/quality
   auditor still need implementation and fault-path tests. The prepared entrypoint,
   collectors and read-only plan below do not authorize bypassing those checks.

## Prepared execution path

`cacheflow.v7_gateway:create_app` requires an explicit process implementation:
`reference` or `epoch`. The new launcher reads a separate ignored
`.cacheflow-v7-implementation` marker. Do not create that marker or change the
supervisor entrypoint while the original study is live. This draft does not run
the launcher. Implementation cannot be switched within an existing process;
previously installed V6 adapters are rejected. Module import alone patches nothing.

Reference mode constructs the exact existing classes. Epoch mode supports only
`packing_reuse`, `packing_ready` and `ready_fifo` and invokes their inherited
selection methods. Policy names stay unchanged so request/metric replay stays
identical; implementation identity is additional mandatory metadata. The first
planned GPU screen below tests oldunion versus epoch-oldunion. Readiness remains
in the original full study and as a supported prototype ablation; it is not
silently promoted or relabelled as the primary candidate.

The `/implementation` route returns the constructor class, original selector
identity and six source hashes captured once at factory construction. A GET does
not hash whatever source happens to be on disk later. The outside-window identity
observer checks those captured hashes against the registered files, process PID,
birth time, actual factory argv and the selected public environment value. Both
boundaries must show the same idle process; the first must have empty history and
zero decision calls. This is construction/process proof, not a complete run audit.

`scripts/v7_run.sh` brackets the unchanged main request/metric/output capture with
those boundaries. It rejects reused run IDs, marks failures and preserves an
existing more-specific invalid marker. `scripts/v7_sglang_bench.py` retains the
exact native replay/reset/sampling/histogram/token accounting and adds explicit
mode arguments, V7 source capture and identity boundaries. Its changes are
enumerated mechanically by `v7_collector_source.py`. Neither collector is used by
the live V6 controller. No V7 replay timing or policy enumeration change is needed.

## Fixed development screen, still unrun

`scripts/v7_epoch_plan.py --plan` prints18fresh-engine configurations: three
arrival seeds101/102/103, with main bundle16/reference-oldunion64/epoch-oldunion64
and native DFS/reference-oldunion64/epoch-oldunion64. Seed102 reverses the six-arm
order;103 swaps the engine blocks. All use the already exposed60-QA V5 development
cohort,6GiBGPU KV,16,000,745,472configuredhostpayloadbytes, native concurrency16,
batch8192, queue512, bypass8, output96, nominal4QPS, thread preparation and uniform
180second read/pool/upstream timeouts with keepalive0. Main lazy heap rounding is
observed separately; it is not exact cross-engine heap/RSS equality.

Each engine is fresh for one measured arm, with60separateFIFO/direct-native warmup
requests before cache reset/fresh gateway. The stage totals1,080measured and
1,080warmup requests, still only60uniqueQA. Native uses pinned FlashInfer/Direct,
the same-batch guard and existing graph settings. It is upstream HiCache with a
documented component adaptation, not complete Strata.

Primary comparisons within each engine/seed are originalunion→epochunion for the
optimization effect and strongbaseline→epochunion for competitiveness. Preserve
strongbaseline→originalunion separately to explain baseline strength. No pairing
with old process measurements, no successful-only failed-arm quantiles, no retry,
and no dropping a completed regression. Freeze the final plan before execution;
this draft is not that freeze.

## Required evidence and subsequent work

- Reconcile prompt/token/trace/model/output hashes, actual engine/cache/transport
  flags, fresh process IDs, warmup separation and all request outcomes.
- Record chooser calls/hits/threadCPU, process CPU, preparation, ingress/admission/
  upstream stages, full scheduled-arrival TTFT/completion, native ITL bucket bounds,
  source-labelled prefill/cache/transfer counters, resources and per-conversation
  waits/bypasses. Missing endpoints remain null; summed CPU/wall counters do not
  become causal latency or DMA savings.
- Grade captured text with the pinned official evaluator; retain per-question
  score/hash/cap changes. Similar means are not quality equivalence.
- Preserve all three arrival seeds and uncertainty assumptions. The development
  population is exposed and small; do not call it fresh semantic confirmation.
- After the screen establishes serving correctness, register matched
  low-reuse/GPU-fit/load/abstention controls and a new full confirmation before
  making a strong contribution claim. Neutral E2E timing on60QA does not refute a
  large-queue scaling hypothesis: this stage cannot substitute for full-workload
  measurements. Preserve the scaling hypothesis and register its full test;
  errors or material regressions require investigation before promotion.
  Full main bundle regressions and native median/conversation penalties in V6
  remain part of the report regardless of V7 outcomes.
- If the screen is negative, retain it and return to profiling. Do not redefine
  success around CPU tests, a synthetic speed ratio or a weaker baseline.
