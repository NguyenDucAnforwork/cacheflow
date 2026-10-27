# Prospective native lookup watermark intervention

2026-10-27. V8 observed actual native PREFETCHING trackers with zero scheduled
tokens/allocated blocks but oversized stored-watermarks, and replayed the STORE
method on seven observed scalar bounds. This establishes a bookkeeping issue;
it does not establish the original stall cause, missed unique backend bytes,
quality equivalence or a competitive scheduler. Original failed runs remain.

## Fixed intervention and identity

Native mode `reference` keeps the installed lookup function. `idempotent` changes
exactly one expression in LMCacheMPConnector.get_num_new_matched_tokens:
`tracker.increase_num_stored_tokens(ret)` becomes
`tracker.num_stored_tokens=max(tracker.num_stored_tokens,ret)`.
All real STORE increment operations, lookup results/control flow, native
allocation/scheduling, gateway policy and prompts remain unchanged. No HOL or
epoch patch. Installed files are never edited. Only a fresh explicit launcher
loads an import hook before connector construction.

Registration pins source/native files, original failures/evidence, full model,
packages, inputs, protocol and exact AST transformation. Prospective semantic
code fingerprints come from compiling native source without importing it. At
actual scheduler/worker connector construction, both modes log the effective
bound method code identity, AST identity, class, role, PID and monotonic clock.
Those proof files and engine PID/birth bracket each actual request ledger.
No per-call observer is added to the four unprofiled arms. Native source drift,
mode flips, wrong class/method/role, missing proof or replaced PID fail closed.

Code hashing uses an explicit canonical serialization of bytecode, constants,
names, parameters, flags, exception table and source location. Python marshal
reference/interning flags are not a canonical identity format. Tests exercise
the actual bound function/prospective fingerprint in both modes without native
imports, repeated lookups, preserved real-store increments, None/zero/preemption
paths, lookup exceptions and source drift.

## Fixed six-arm graph

The exact graph is `scripts/v9_repair.py plan`:

| Order | Scope | Mode | Arrival seed | Targets | Native probe |
| --- | --- | --- | --- | ---: | --- |
| 1 | Development diagnostic | Reference | 101 | 60 | On |
| 2 | Development diagnostic | Idempotent | 101 | 60 | On |
| 3 | Full diagnostic | Reference | 901 | 1986 | Off |
| 4 | Full diagnostic | Idempotent | 901 | 1986 | Off |
| 5 | Full diagnostic | Idempotent | 902 | 1986 | Off |
| 6 | Full diagnostic | Reference | 902 | 1986 | Off |

Every arm gets a fresh vLLM/LMCache,60separateFIFOwarmups under that arm's native
mode, then reset/fresh V6 gateway before measurement. Total8064targets and360
warmups. All inputs/seeds/QA are already exposed; no new semantic holdout claim.
Reference/candidate order reverses for the second full arrival seed. No retries,
selection of successful subsets, reused output or shared warm cache across arms.

All arms use pinned Qwen3-4B, BF16,96output cap,6GiBGPU KV,
48002236416configured CPU bytes (observed lazy heap48049946624),maxseq16,
batch8192,CUDA graphs,union64,queue512,bypass8,thread preparation and4QPS.
Uniform600s client read/pool and gateway upstream-read timeout,keepalive0.
This differs from3600s primary study. Every arm is diagnostic and marked invalid
for primary performance before requests; successful-only failed-run latency
summary fields are retained private bytes, never a complete-cohort comparison.

The first two arms reuse the four V8 metadata hooks at2s sampling, with no extra
future/event query/sync/tensor access. Eligible samples are PREFETCHING with
zero scheduled/allocated tokens and a positive lookup prefix. Require eligible
samples in both modes, observed inflation in reference and none in candidate.
Missing coverage is inconclusive/failure, never zero inflation by assumption.
Probe counts do not measure total incidence, backend STORE bytes or DMA time.
No probes in four full arms; both modes uniformly tee native engine logs.

## Execution and evidence

Wait for exact V8diag3 controller termination or verify actual process absence
and its terminal complete diagnostic record. It must retain four outcomes and
clean cleanup. Require all services idle/GPU<1GiB before each fresh engine;
hash model weights only outside inference. No second engine. Original V7 GPU
gates/failures are unchanged; this is an explicitly different repair diagnostic.

Whole client/error/output ledgers, exact prompt/token hashes, source config,
native method bookends, gateway coverage and missing records are retained.
Successful complete targets additionally require prompt-source reconciliation
and official per-request LoCoMo scores/category5/cap hits. Failed workloads are
not scored on successful subsets. Missing metric endpoints stay null; source
counters and sampled CPU/RSS are not DMA. Native ITL/fairness/strong-baseline
primary audits still belong to subsequent performance confirmation.

Warm failure, source/identity/integrity/probe validation failure stops the graph;
expected target request errors remain outcomes. Every cleanup attempts all
inference services and restores both supervisor configs, retaining errors.
After execution, independently recheck all six raw/effective-code/evaluator
artifacts, fresh process units and fixed pair identities before interpreting
outcomes. No raw deletion/archive before the appropriate audit.

## Limits and subsequent work

A corrected metadata invariant or a few successful full runs is not a proof of
production liveness or a strong research contribution. Retain median/quality/
conversation regressions and all failed scope. Next steps still require actual
epoch GPU/strong main bundle/native DFS comparisons, matched controls, full
confirmation, reproducible report and Vietnamese interview documentation.
