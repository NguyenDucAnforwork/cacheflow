# CacheFlow: reproducibility log

> **Measurement correction,15:38UTC:** LMCache default lazy allocator rounds its heap to64MiB. Configured-byte flags match native payload, but actual cross-engine heap parity is not established: current main repeat reports16039018496bytes vs native16000745472bytes (+.2392%). Full main48049946624bytes is a source-derived prediction vs native48002236416 (+.0994%), not yet observed. Within-engine policy arms remain matched; do not make causal cross-engine timing comparisons. See `results/v3/v5_host_allocator_rounding.json`. The sealed plan is preserved with this external correction. The stalled main repeat was manually aborted; no full study has started.

Status: pinned stack installed and development replay verified on `optim`. This file records both the initial host audit and the commands used after setup.

## Host snapshot (2026-10-22)

```text
GPU: NVIDIA GeForce RTX 3090, 24576 MiB
RAM: 247 GiB total, 183 GiB available
/workspace: 20 GiB free, overlay; workspace_is_volume=false
Python: 3.12.3
PyTorch: 2.11.0+cu128
vLLM: absent
LMCache: absent
```

Before setup, record exact vLLM/LMCache versions and wheel ABI, model revision/hash, CPU L1 budget, GPU KV budget, tokenizer revision, and host memory/disk headroom. Use an isolated environment and keep Hugging Face cache under /workspace with disk monitoring. Keep secrets out of this file and Git.

For every benchmark run, record: run ID, Git SHA, model/tokenizer revision, vLLM/LMCache versions, server and policy configs, corpus hash, trace seed, warm/cold reset method, arrival schedule hash, metric snapshot paths, and raw output paths. The verified launch and replay commands follow below. Never substitute untested commands for reproducible ones.

## Pinned setup and verified B1 smoke

Exact Python environment: `/venv/main/bin/python` 3.12.15, PyTorch 2.11.0+cu128. Model: `Qwen/Qwen3-1.7B` revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`. Initial root disk had 20 GiB free; check `df -h /workspace` before repeats.

Installation used `uv pip install --index-strategy unsafe-best-match --python /venv/main/bin/python 'vllm==0.22.0' 'lmcache==0.5.3' 'transformers==5.6.2' 'torch==2.11.0+cu128' 'torchaudio==2.11.0+cu128' 'torchvision==0.26.0+cu128' --extra-index-url https://download.pytorch.org/whl/cu128` with `UV_CACHE_DIR=/workspace/.uv-cache`. The CUDA 13 runtime library directory is prepended by `scripts/serve_vllm.sh` and `scripts/serve_lmcache.sh`.

The serving scripts expect the pinned model snapshot under `/workspace/.hf_home/hub/`. On a fresh host after installing dependencies, populate it with `HF_HOME=/workspace/.hf_home /venv/main/bin/python scripts/download_model.py`; then verify the printed path ends in `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`. This helper was added after the original model download and was not rerun on the stopped instance; it uses the documented Hugging Face `snapshot_download` revision API: https://huggingface.co/docs/huggingface_hub/main/guides/download . Keep the model cache and token outside Git.

B1: `./scripts/serve_vllm.sh B1`; probe: `python scripts/smoke.py http://127.0.0.1:8000`. LMCache MP: `./scripts/serve_lmcache.sh`; metrics at `http://127.0.0.1:18080/metrics`. Do not infer B2 success from LMCache server health alone.

## CPU-restore verification and managed services

Install supervisor programs with `./scripts/install_services.sh`, then select mode with `./scripts/set_mode.sh B2 fifo`. The mode script waits for localhost health endpoints. `PYTHONPATH=/workspace/src /venv/main/bin/python scripts/restore_probe.py` stores a common prefix, waits for LMCache, resets only vLLM's local cache through `/reset_prefix_cache`, then sends a related prompt. Verified deltas are in `results/raw/restore_probe.json`. `./scripts/run_benchmark.sh RUN_ID WORKLOAD INPUT_TOKENS GROUPS PER_GROUP OUTPUT_TOKENS` records client results, a metrics time series and registry row. Run it from `/workspace` after setting the mode; exact benchmark corpus/trace SHA will be written by the runner.

## Development screening runs

From a clean stack, `./scripts/set_mode.sh B2 fifo && ./scripts/run_benchmark.sh b2-longdoc-8k-r1 long_doc 8192 8 4 64`; then `./scripts/set_mode.sh B3 dhas && ./scripts/run_benchmark.sh b3-longdoc-8k-r1 long_doc 8192 8 4 64`. Source SHA for both: `9be600cfbdce4e70a94ae9451987420e688d3d9b`. Trace SHA is recorded in both summaries and must match for paired comparison. Analyze with `PYTHONPATH=src python -m cacheflow.analyze results/raw/b2-longdoc-8k-r1.jsonl results/raw/b3-longdoc-8k-r1.jsonl --output-dir results/figures/dev-screen`. This was a development screen; there was no CPU restore during the replay.

## Revisit and negative-control pairs

Use `./scripts/set_mode.sh MODE POLICY` before **each** run to clear both tiers by restarting the serving stack. The 8K revisit pairs used `./scripts/run_benchmark.sh RUN_ID long_doc_revisit 8192 8 4 64` with order `b3-revisit-8k-r1`, `b2-revisit-8k-r1`, `b2-revisit-8k-r2`, `b3-revisit-8k-r2`; all four summaries record source SHA `cc1ae6536f8ad6cddfc0995fedf8b0ec4f4cffa4`. The 2K distinct-prefix pairs used `./scripts/run_benchmark.sh RUN_ID distinct 2048 8 4 64` with order `b2-distinct-2k-r1`, `b3-distinct-2k-r1`, `b3-distinct-2k-r2`, `b2-distinct-2k-r2`; source SHA `46fb90a212e4a90579c66a89e8127fec877d8fcb`. Policy is `fifo` for B2 and `dhas` for B3. All traces and metrics are under `results/raw/` and aggregate JSON/figures under `results/figures/`.

Compare each pair with `PYTHONPATH=src /venv/main/bin/python -m cacheflow.analyze results/raw/B2_RUN.jsonl results/raw/B3_RUN.jsonl --output-dir results/figures/PAIR`. Audit whether a delay-hit candidate could have reached the first-token signal within the 200 ms bound using `PYTHONPATH=src /venv/main/bin/python -m cacheflow.diagnose_delay results/raw/gateway.jsonl B3_RUN`. Generate one phase figure with `PYTHONPATH=src /venv/main/bin/python -m cacheflow.plot_timeline results/raw/b3-revisit-8k-r2.jsonl results/figures/revisit-r2/critical_path.png --group doc-0`. The timeline uses client scheduled arrival and first/complete timestamps plus gateway dispatch timestamps; LMCache reads are sampled once per second, so its vertical markers are approximate windows, not transfer duration measurements.

## Matched tier baseline commands

Run order was B0 r1 → B1 r1 → B2 r3 → B1 r2 → B2 r4. Each mode was reset before its run: `./scripts/set_mode.sh B0 fifo` or `B1 fifo` or `B2 fifo`, then `./scripts/run_benchmark.sh RUN_ID long_doc_revisit 8192 8 4 64`. `results/raw/*.summary.json` records exact run IDs, Git HEAD and common trace SHA. The first B0 attempt stopped after setup because `supervisorctl status` returned a nonzero code for intentionally stopped LMCache; it produced no benchmark rows. The B0/B1 launcher status check was repaired before the five successful runs, but the benchmark summaries still contain the preceding committed HEAD. Commit `ac328da` contains the exact launcher fix; this did not alter the engine or gateway code paths used in the measurements.

## Simultaneous arrivals and live-engine crossover

`long_doc_simultaneous` keeps the 8K document prompts and question IDs but schedules each document's four questions at the same millisecond. The two cold-restart pairs used `./scripts/run_benchmark.sh RUN_ID long_doc_simultaneous 8192 8 4 64` with order `b2-simultaneous-8k-r1`, `b3-simultaneous-8k-r1`, `b3-simultaneous-8k-r2`, `b2-simultaneous-8k-r2`, Git SHA `58e6ea5cd1043e344678f5d378a4300c6167d756`.

For the lower-noise crossover at the next source checkpoint, run `bash scripts/run_crossover.sh` from `/workspace`. It starts one two-tier engine, records its vLLM and LMCache PIDs in `results/raw/crossover_pids.csv`, and executes B2→B3→B3→B2 without restarting either process. Before every measured replay it sends the same two-request direct-vLLM warmup, waits for asynchronous stores, verifies the gateway is idle, clears LMCache L1 through `POST /cache/clear`, clears GPU prefix state through vLLM `POST /reset_prefix_cache`, and checks the L1 gauge is zero. `scripts/set_policy.sh` restarts only the gateway to switch policy. This protocol uses localhost-only control endpoints; never call the force-clear API with active requests. The policy reset is distinct from the earlier full-service cold reset and both result sets remain in the registry.

## Separate OTLP profile

With the committed supervisor configs installed by `bash scripts/install_services.sh`, run `bash scripts/profile.sh`. The script starts the localhost OTLP sink, enables tracing only for its fresh B2 LMCache process, replays one 8K revisit trace, then stops the paid GPU services and sink in a cleanup trap. Raw spans are in `results/raw/otlp-profile.jsonl`; the profile benchmark is `results/raw/b2-profile-8k-r1.*` and must not be used in a timing A/B comparison. Regenerate the operation plot with `PYTHONPATH=src /venv/main/bin/python -m cacheflow.plot_otlp results/raw/otlp-profile.jsonl results/figures/otlp_profile.png`. The pinned LMCache 0.5.3 build exports inclusive `mp.retrieve` but no staging/kernel child spans, so exact H2D time is unavailable.

## Readiness guard development and holdout

The refinement is a separate `dhas_guarded` gateway policy at SHA `5280c74`; original `dhas` remains available. Run `bash scripts/run_guard_dev.sh` for the six-run seed 7 development crossover, or `bash scripts/run_guard_holdout.sh` for the six-run seed 11 holdout. Both scripts preserve vLLM/LMCache PIDs while changing only the gateway policy, warm identically and clear caches before every run. PID registries are `results/raw/guard_dev_pids.csv` and `results/raw/guard_holdout_pids.csv`. Analyze a pair with `PYTHONPATH=src /venv/main/bin/python -m cacheflow.analyze results/raw/B2.jsonl results/raw/B3G.jsonl --output-dir results/figures/PAIR`; audit guard decisions with `PYTHONPATH=src /venv/main/bin/python -m cacheflow.diagnose_delay results/raw/gateway.jsonl RUN_ID`. Source SHA in each benchmark summary is the commit immediately before that benchmark; scripts and docs may be committed afterward.

The frozen seed 11 holdout used `bash scripts/run_guard_holdout.sh` at source SHA `5280c74`; its trace SHA and full run order are recorded in `docs/main_results.md`. All six first metrics samples show zero LMCache L1 usage and GPU KV occupancy, and all rows in `results/raw/guard_holdout_pids.csv` list the same serving PIDs. Figures and paired JSON summaries are in `results/figures/holdout-{guard1,guard2,original1,original2}/`. Diagnose each guarded run from the append-only `results/raw/gateway.jsonl` using its exact run ID.

## GPU KV capacity sweep

Run `bash scripts/run_capacity_sweep.sh` from `/workspace`; it executes B1/B2 twice at 4 GiB and 8 GiB, with full service restarts and fixed seed 7/8K revisit requests. The script writes the budget to an ignored `.cacheflow-gpu-kv-bytes` marker, records `results/raw/capacity_sweep_config.csv`, and removes the marker/stops GPU services in its exit trap. `scripts/serve_vllm.sh` accepts only 4, 6, or 8 GiB to prevent accidental unbounded allocation. The 6 GiB runs in `configs/capacity_matrix.csv` are older matched baselines; source SHA is in each `.summary.json`. Regenerate the combined metric CSV and plot with `PYTHONPATH=src /venv/main/bin/python -m cacheflow.plot_capacity configs/capacity_matrix.csv --output-dir results/figures/capacity`. Raw pair figures/JSON are under `results/figures/cap4-r{1,2}` and `cap8-r{1,2}`.

## Working-set and quality controls

`bash scripts/run_workingset_sweep.sh` replays seed 7 `long_doc_revisit` with 12 groups × four questions at the fixed 8 GiB GPU KV budget, order B1→B2→B2→B1. It writes `results/raw/workingset_12doc_config.csv`, removes its ignored budget marker, and stops all GPU services on exit. The source SHA for all four runs is `37056f9`; pair JSON/figures are under `results/figures/workingset12-r{1,2}`. Rebuild the eight-versus-12-document plot and metric CSV with `PYTHONPATH=src /venv/main/bin/python -m cacheflow.plot_workingset configs/workingset_matrix.csv --output-dir results/figures/workingset`.

Run `PYTHONPATH=src /venv/main/bin/python scripts/run_quality_audit.py` to regenerate `results/quality_audit.jsonl` for 18 declared pairs. For any other pair, use `PYTHONPATH=src /venv/main/bin/python -m cacheflow.quality results/raw/A.jsonl results/raw/B.jsonl`. The audit checks trace/prompt hashes, request IDs, status, input/output token counts and output hashes. It cannot inspect semantic equivalence because the benchmark records hashes rather than generated text.

## Instance state at handoff

The Vast.ai instance `57086282` was stopped at about 2026-10-21 19:40 UTC after all GPU services ended. `/workspace` data is expected to persist on the stopped instance, but SSH is unavailable until it is restarted and a GPU is assigned. The private GitHub branch `feat/cacheflow-6h` contains code, raw measurements, figures, and the five living docs; model weights and the Python environment are not in Git. Vast documents that stopped instances continue storage billing: https://github.com/vast-ai/docs/blob/main/guides/instances/manage-instances.mdx . Use the GitHub repository as the durable record before restarting or destroying the rental.

## Decision-stratified guard audit

For a holdout comparison, run `PYTHONPATH=src python3 -m cacheflow.stratify_guard results/raw/gateway.jsonl BASELINE_RUN GUARDED_RUN --output results/figures/PAIR/guard_phase_by_decision.json`. The committed artifacts cover both FIFO→guard and original-DHAS→guard comparisons for seed 11. It classifies each request from the guard's logged decision and reports paired mean deltas for arrival→dispatch, dispatch→first token, and total arrival TTFT. The phase decomposition is descriptive; it does not remove whole-run drift.

## Prompt-token source accounting

Regenerate the B0–B4 stacked token-source plot with `PYTHONPATH=src python3 -m cacheflow.plot_cache_accounting configs/cache_accounting_matrix.csv --output-dir results/figures/cache_accounting`. The script uses live-metric deltas and checks that GPU-hit + CPU-hit + newly computed prefill tokens equals total prompt tokens for each run; it refuses a matrix that mixes trace hashes. The five selected rows are representative runs from different execution blocks, so use this plot for cache-source accounting only.

## Observed readiness-window sweep

Run `PYTHONPATH=src python3 -m cacheflow.readiness_sweep configs/readiness_sweep.csv --output-dir results/figures/readiness` to rebuild the CSV and plot for four trace families. It invokes the logged-producer audit at each candidate window and at `window − 20 ms` to account for the configured grace. The line shows the share of observed matching producers whose first token plus grace would fit inside a given bound; it does not simulate how another bound would alter request execution, cache-store visibility, or throughput.

## Admission-deadline audit

Run `PYTHONPATH=src python3 -m cacheflow.audit_admission configs/admission_audit.csv --output results/figures/admission_audit.csv`. The script reports queue-wait p50/p90/max and count/tail above the configured 200 ms intentional-deferral deadline for ten selected runs; it checks newer logged overrun fields against the value reconstructed from arrival and dispatch times. The older gateway trace schema lacks explicit deadline fields, so the reconstruction assumes the pinned `max_wait_ms=200` policy config. Compare FIFO and DHAS rows before attributing over-bound waits to policy deferral.

## Current V5 protocol and evidence (2026-10-26)

Earlier sections retain historical V1/V2 commands and paths. Current worktree is `/workspace/cacheflow-e1`, branch `feat/cacheflow-v3-competitive`, modelQwen3-4B revision`1cfa9a7208912126459214e8b04321603b3df60c`. Model/data paths, installed versions, source snapshots and actual arguments are captured by each run's setup. Main environment is `/venv/main`; nativeSG is isolated at `/venv/sglang-baseline`. Do not install another serving stack over either environment.

Current protocol is [V5_PROMPT_REPAIR_PLAN.md](V5_PROMPT_REPAIR_PLAN.md), with immutable seal`results/v3/v5_prompt_freeze.json` SHA256`19f3fc70db3ba44df24b99dd64ae02b9dfe220bf1a434e54553b1bbf1b4e8271`. V5 changes the contradictory user abstention footer and uniformly records3600s transport timeouts/client keepalive0; it does not alter the fixed union policy. Revision1 source/plan/seal and the ReadError are archived separately. The historical V4 verifier intentionally rejects the documented transport additions; use the V5 verifier.

Read-only protocol/plan/test checks:

```bash
PYTHONPATH=src /venv/main/bin/python scripts/v5_verify.py
PYTHONPATH=src /venv/main/bin/python scripts/v5_validate.py --plan
PYTHONPATH=src /venv/main/bin/python scripts/v5_confirm.py --plan
PYTHONPATH=src /venv/main/bin/python scripts/v5_full.py --plan
PYTHONPATH=src /venv/main/bin/python -m pytest -q
```

`--plan` prints the actual fixed action graph without starting services. The executing controller is `scripts/v5_pipeline.py`:57validation→audit→27repair-repeat→audit→17full→audit. All measured request errors invalidate their run; there are no request retries or successful-only percentile tables. Each ID refuses overwrite. These exact IDs have already been used on this instance: rerunning the controller here is not a reproduction shortcut. A new independent replay needs a fresh recorded namespace/prospective plan and source/trace provenance, without replacing any historical artifact. Confirm current jobs via actual process/supervisor state before any GPU action; never run the two GPU stacks concurrently.

Recompute complete validation evidence from retained private raw outputs:

```bash
PYTHONPATH=src /venv/main/bin/python scripts/v5_audit_validation.py
PYTHONPATH=src /venv/main/bin/python scripts/v5_analyze_main.py
PYTHONPATH=src /venv/main/bin/python scripts/v5_analyze_decode.py --validation --output results/v3/v5r2_validation_secondary_metrics.json
PYTHONPATH=src /venv/main/bin/python scripts/v5_run_intervals.py
PYTHONPATH=src /venv/main/bin/python scripts/v5_analyze_waits.py results/v3/v5r2_validation_audit.json --output results/v3/v5r2_validation_waits.json
PYTHONPATH=src /venv/main/bin/python scripts/v5_plot_primary.py
PYTHONPATH=src /venv/main/bin/python scripts/v5_plot_main.py
```

These commands analyze existing data; audits reject missing source/token/output/configured-budget coverage; configured flags do not prove actual allocator capacity, as corrected above. The official evaluator version/SHA is embedded in quality artifacts. Raw generated text stays captured privately; no posthoc answer extraction or normalization was introduced. Repeated seeds reuse fixed questions; means of run quantiles and exploratory n3 intervals must retain those labels.

After all27repair repeats exist, `v5_audit_confirmation.py` and `v5_analyze_confirmation.py` produce integrity/quality and all18contrasts including fresh-processDFS. `v5_analyze_decode.py --stage confirmation --output results/v3/v5r2_confirmation_secondary_metrics.json` and `v5_run_intervals.py --stage confirmation` extend secondary metrics to that stage. Full equivalents use`--stage full` and require the complete17-run audit, not an incomplete subset. Conv43/44 repair repeats are not a new semantic holdout.

The separate `v5_full_histograms.py PIPELINE_PID` is a passive observer registered before full request arrivals. It verifies the live controller identity, waits on setup markers and takes two native metrics snapshots outside each measured request window. It never starts/resets engines or changes parameters. Exact prompt-token delta, response-window clock and enginePID determine coverage. `v5_analyze_histograms.py SNAPSHOT... --output OUTPUT.json` rejects invalid cumulative buckets and gives quantile bounds. `results/v3/v5_native_itl_semantics.json` hashes installed native sources: SG token-weighted update averages and vLLM engine-output intervals must not be pooled or confused with client-token timestamps.

`v5_after_pipeline.py PIPELINE_PID` waits on a verified live controller and analyzes complete audits only after it exits. It cannot retry/start serving work or mark the research complete. It derives completion, waits, run descriptors, per-conversation QoS, native resource samples and available full ITL snapshots; missing histogram coverage remains explicit. Final scientific review, plots/report and requirement audit still follow.

Direct and kernel profiling artifacts remain separate from serving comparisons. Do not rerun heavy profilers while latency experiments are active. Direct DMA coverage is incomplete; kernel overlap is a scoped GPU-clock interval measurement. Preserve raw failures, output text, metric samples and trace manifests before any cleanup or instance recycle. Current state lives in [PROGRESS.md](PROGRESS.md), not the historical instance-state section above.

### Separate main liveness diagnostic after V5 retirement

The original pipeline terminated after an explicitly recorded manual abort; no full study ran. `v5_audit_manual_abort.py` verifies40retained client/output records and27completed gateway records while excluding successful-only quantiles.13RemoteProtocolErrors after controlled gateway stop are manual interruptions, not natural3600s timeouts. See `v5r2_main_stall_manual_abort.json`, `_main_manual_abort_audit.json` and `_pipeline_retirement.json`.

Read the registered diagnostic action graph without GPU mutations:

```bash
PYTHONPATH=src /venv/main/bin/python scripts/v5_stall_diagnostic.py --plan
PYTHONPATH=src /venv/main/bin/python -m pytest -q tests/test_v5_liveness_probe.py
```

Execution uses `--after-pid VERIFIED_LIVE_PIPELINE_PID`, registers all sourceSHA before waiting, and starts only after the prior pipeline is terminal with its retained diagnostic outcome. The current namespace is already registered: do not run a second controller. OffA/on/offB each starts a fresh main stack, warms identically and replays the same three historical arms before the failing seed702target. All use180s diagnostic timeouts and are excluded from primary comparisons. On-phase temporarily selects `v5_serve_vllm_probe.sh` through supervisor; the original supervisor command/config bytes are restored and serving stopped on completion. Original upstream source files and sealed actors are unchanged.

Probe journals are private `results/v3/raw/v5diag-stall1-probe.PID.jsonl`. Analyze after completion with `v5_analyze_liveness_probe.py --output results/v3/v5diag_stall1_probe_analysis.json`; use`--partial` only for explicitly partial inspection. A complete analysis must inspect both native component coverage, probe errors and off/on/off outcomes. Missing state is not zero. No snapshot alone establishes successful DMA, tensor correctness or root cause. In this container gdb attach was unavailable; do not alter ptrace/sysctl permissions to work around that restriction.

### V6 readiness pilot (development, not full evaluation)

V5 actors/seal remain byte-identical. The separate `cacheflow.v6_gateway:create_app` factory installs process-local policy dispatch for`packing_ready`and`ready_fifo`; parent policy constructors remain unchanged. `v6_runtime.py` uses original runtime generation then explicitly selects a new policy in its gateway config/marker. The serving wrapper differs only by the factory target. This opt-in adapter is a new method runtime: its argv and all V6 source fingerprints must be verified even though the historical V5 byte verifier passes.

```bash
PYTHONPATH=src /venv/main/bin/python scripts/v6_pilot.py --plan
PYTHONPATH=src /venv/main/bin/python -m pytest -q tests/test_v6_ready_scheduler.py
```

The registered`v6pilot2-*`namespace is already running; do not start another controller. Two blocks use dev60QA/seed101 and already-exposed stress40QA/seed702, reversing the four-arm order. FIFO64, originalunion64, readiness-onlyFIFO64 and gatedunion64 all receive fresh gateway/cache resets, the same model/resources/preparation and180s pilot timeouts; engines restart between dataset blocks. Native probes/profilers are off. The controller records actual gateway argv/V6 source hashes in each`*.v6_entrypoint.json`, captures native host allocator status and restores original gateway supervisor config after completion. It stops a block on any failed/incomplete run and never retries it.

Only after all8measured arms exist, run`PYTHONPATH=src /venv/main/bin/python scripts/v6_audit_pilot.py`. It checks parent19source coverage plus new entrypoint/source/policy/reset/transport/budget/observer evidence, grades captured outputs officially, and derives paired TTFT, completion and decode proxies. A partial pilot cannot produce a complete audit. These100uniqueQA reuse previous development exposure; no fresh semantic holdout, three-seed confirmation or full contribution claim is implied. No V5/V6 pooling.

The first`v6pilot1`attempt is retained as an integration failure: parent replay argparse did not accept either new policy, so no new-policy request was sent. Registered five-source snapshots are archived in`v6pilot1_source_archive.json`. Replacement`v6pilot2`adds a replay module with only those two CLI enum entries and two mechanically checked shell launch-target substitutions. Parent files stay byte-identical. Controller preflight verifies both policy names and exact source transformations before GPU. The replacement reruns the entire fixed pilot; earlier baseline results are not pooled. `v6_after_pilot.py VERIFIED_PILOT_PID` waits on the verified current controller then audits all eight completed arms only, without GPU retries/restarts.

### Strong V6 main development matrix and passive native ITL

`v6pilot2_audit.json` accepts all8measured arms400requests plus official scores; no primary GPU replay was needed when a print-only analysis key was corrected. The registered three-seed matrix is now running under`v6dev1-main-*`: eight policies×three seeds, fresh engine/LMCache per arm, identical60devFIFO warmup, empty-cache reset and fresh gateway,180s uniform dev transport. Warmups1440requests remain separate from1440measured requests on60uniqueQA. Original/shared-process protocols are not pooled. Failed independent arms are retained, then the next preplanned arm starts its own fresh engine; no retries.

```bash
PYTHONPATH=src /venv/main/bin/python scripts/v6_main_matrix.py --plan
```

Do not start a second controller for the existing namespace. `v6_after_main_matrix.py VERIFIED_LIVE_MATRIX_PID` waits for terminal status and runs`v6_audit_main_matrix.py`; it requires all24measured and24warmup outcomes/source/token/output/resource/observer contracts before emitting complete comparisons. Failure/missing coverage emits an incomplete artifact. Native probes and GPU profilers are off.

`v6_main_histograms.py VERIFIED_LIVE_MATRIX_PID` is separately registered passive observation. It takes no retrospective baseline for setup markers already present, and two metrics GETs for future arms outside request windows. SamePID, before/after clocks and exact prompt/generation-token deltas determine native coverage. Count/sum/buckets must be monotonic/complete; missing coverage staysnull. Main audit includes native engine-update mean and bucket bounds separately from primary metrics. This is not an individual-client-token timestamp trace or exact percentile interpolation. The current observer is already live; avoid duplicate collectors.

### Canonical request-ledger indexes

The historical append-only main CSV has a35column header and later38column rows after transport metadata was added; nativeSG also has mixed legacy widths. It is preserved as raw history and must not be read as a single stable positional schema. Per-run JSON summaries and per-protocol strict audits are authoritative. Build separate named-column indexes without changing any active writer or historical record:

```bash
PYTHONPATH=src /venv/main/bin/python scripts/v6_normalize_registry.py
```

`results/v3/registry_normalized.csv` and`results/v3/sglang/registry_normalized.csv` derive a union header from JSON keys, retain summary path/SHA and invalid-marker status, and leave unavailable values blank. They hide successful-only latency quantiles for explicitly failed/invalid entries while preserving raw JSON. Their audit JSON reports legacy width counts, duplicate IDs and incomplete summaries. They are request-ledger locators, not automatic performance-eligibility or independent-QA counts; failures before replay require controller outcomes. Rerun after jobs end; the main-matrix auditor does this automatically. A regression test verifies mixed schema normalization, raw preservation and blank invalid latency fields.

## V6 continuation and full-study execution

The24-arm main development matrix is terminal and audited in `results/v3/v6dev1_main_audit.json`; render its checked figure with `PYTHONPATH=src /venv/main/bin/python scripts/v6_plot_main.py`. It is a60-QA development study, not a completed full benchmark. Native `v6native1` is active; inspect verified process handles and current registrations before any GPU action. Do not manually launch another engine or rerun an existing namespace.

Read-only graphs: `scripts/v6_native_matrix.py --plan` (60arms2700requests), `scripts/v6_main_controls.py --plan` (36arms1260requests), and `scripts/v6_full.py --plan` (30full arms59580requests), all via `PYTHONPATH=src /venv/main/bin/python`. The expanded controls preserve originalunion and readiness under matched regimes. Native/maincontrol run-level processes differ as documented; do not pool results across stages.

The queued dependencies require complete stage audits and idle services, then `scripts/v6_freeze_full.py` checks primary low-reuse gates and seals actors/model weights+tokenizer/input/protocol/package evidence before any full GPU work. `docs/V6_FULL_PROTOCOL.md` is the prospective protocol. A seal is not a successful run. The full controller uses independent fresh engines, separate warmups,3600s uniform transport, no retries, and complete per-run integrity/official quality audit before lossless raw archival. Rejected/missing audits stop the dependency rather than restarting serving work.

After full completion, `scripts/v6_audit_full.py` reopens all raw archives and verifies the30run/59580request stage before constructing matched comparisons. Archive manifests retain original/compressed SHA and associated complete audit hashes. Existing raw is never replaced with aggregate-only evidence. The normalizer reads compressed summaries without expansion; `summary_file_sha256` hashes the stored gzip/plain file, while `summary_uncompressed_sha256` preserves exact JSON bytes. Do not edit sealed actors/protocol/manifests or immutable archive-linked audits; corrections need separately recorded analysis/provenance. Full results/report/research completion remain unproven until the actual artifacts pass.

The native primary subset now has independently audited seed101/102/103blocks. `scripts/v6_audit_native_checkpoint.py --seed SEED` verifies one completed block against its separately named official-quality artifact; `scripts/v6_analyze_native_primary.py` combines the3audits without claiming the complete60-arm stage. `scripts/v6_plot_native_primary.py` renders the inspected primary tradeoff plot. These are read-only with respect to serving; they never replay requests.

`PYTHONPATH=src /venv/main/bin/python scripts/v6_input_oracle.py` reconstructs exact causal block-prefix counts from the60-QA input trace using the pinned local tokenizer. `scripts/v6_native_tokenizer_parity.py` runs under `/venv/sglang-baseline/bin/python` with the serving wrapper's existing cu13 library path, compares native-loader token vectors onCPU and writes provenance. It does not start a GPU engine. The current parity covers60development prompts; the full1,986-QA cross-environment preflight is now mandatory before full freeze. Published registrations intentionally block overwrite; use the independent namespace constructor below once the reference full seal exists. Do not remove original evidence to bypass those guards.

## Full input preflight and independent execution namespaces

The full freezer now invokes `scripts/v6_full_input_preflight.py` after development gates pass and services are idle. It streams1,986prompts through the pinned main and native tokenizer loaders, compares every token ID, and checks the same prompt/input/output budgets across all3arrival traces. `--plan` is read-only. The current2-prompt smoke has `complete_trace=false`; it cannot satisfy full preflight. Attempt fingerprints and registration are retained, with exact hashes linked into the final full seal. This CPU stage is not model serving or a benchmark result.

Once `results/v3/v6full1_freeze.json` exists and its reference source/input/model evidence still matches the checkout, these commands prepare a new independent execution namespace from the repository root:

```bash
PYTHONPATH=src /venv/main/bin/python scripts/v6_reproduce_namespace.py v6repeat1 --reference-freeze results/v3/v6full1_freeze.json
PYTHONPATH=src /venv/main/bin/python scripts/reproductions/v6repeat1/v6_full.py --plan
```

Preparation writes copied controller/audit/preflight modules, a separate protocol and `namespace_manifest.json`. It never calls supervisor or removes earlier results. An AST check permits only namespace/path string replacements and a fixed import-path bootstrap; the30-arm graph must preserve every setting except run IDs. Parent/transformed/generator/protocol/reference hashes are recorded. An existing namespace or changed reference evidence is rejected. Commit the generated bundle/protocol as the new study provenance.

After all serving services are idle, the new namespace requires its own prospective seal and execution:

```bash
PYTHONPATH=src /venv/main/bin/python scripts/reproductions/v6repeat1/v6_freeze_full.py
PYTHONPATH=src /venv/main/bin/python scripts/reproductions/v6repeat1/v6_full.py
```

The independent run preserves original development prerequisites/gates and model/prompt/budget/arrival/transport/method settings. It repeats the full study rather than overwriting or stitching selected earlier arms. Numerical timing and ordinary temperature0outputs can still differ between runs. CPU tests verify source/plan equivalence, actual generated CLI imports and collision/algorithm-change rejection; no additional reproduction GPU study has been executed. The original full study itself remains unrun at this checkpoint.

Digest identities are typed by representation: registration `trace_sha256` is a file-byte hash, replay/manifest `trace_sha256` is canonical V2TraceRow-array identity. Use `v6_trace_hashes.scan` for stored/uncompressed/canonical hashes rather than comparing these strings across domains. The unsealed native auditor/fullpreflight comparison bug was corrected before their terminal execution, without replaying GPU requests; completed main/nativeprimary audits were not affected. `v6_audit_native_subset.py REGIME` verifies complete3seed controls while the overallstage may still be live. `v6_plot_native_controls.py` renders the inspected DFS/load/reuse/GPUfit comparisons.


For a complete main control while other regimes remain live, run `PYTHONPATH=src /venv/main/bin/python scripts/v6_audit_main_controls_subset.py REGIME`, where REGIME is lowload, lowreuse, gpufit or abstention. It requires all nine measured arms and their warmups, validates all registered actors/inputs and the linked native audit, grades captured outputs and writes separately named subset artifacts. Missing/failed arms produce an incomplete record and no success table. It leaves `v6_audit_main_controls.py` and its terminal supervisor-restoration/full36-arm gate unchanged. The lowload subset (540 measured/540 warmup) is complete; the whole main stage remains pending. `scripts/v6_plot_lowload.py` plots within-stack main/native lower-load contrasts; `v5_analyze_waits.py` accepts the subset audit to reconstruct additive stages.

`PYTHONPATH=src /venv/main/bin/python scripts/v6_rehearse_archival.py` exercises integrity/official quality/archive/expansion on temporary byte-identical copies of one completed native 60-QA run. It checks every raw byte and full quality JSON before/after, records implementation/evaluator/source hashes and verifies original raw unchanged. Temporary copies are removed. This sends no inference requests and is not a full48GB execution result; see `results/v3/v6_archival_rehearsal.json`.


Before the first full seal, the freezer's low-reuse integration was corrected to consume the actual main (`p95_ms_delta_pct`) and native (`p95_delta_pct`) schemas separately. It requires complete audits, unique seeds101/102/103 and finite numeric changes, preserving the existing5% primary threshold and separately recorded readiness status. Tests reject wrong schemas/coverage/nonfinite data and distinguish primary failure from a readiness ablation failure. They do not substitute for actual main low-reuse measurements.

The prospective full seal now has separate `analysis_source_sha256` entries as well as serving actor fingerprints. These include per-run/final/config/integrity/quality/resource/fairness/decode/histogram/wait/interval/index code and the pinned official evaluator. Analysis dependency versions are also captured. Full verification and namespace preparation reject changes to this reference analysis; any later correction requires separately recorded provenance. No full seal or full performance result exists yet.


`PYTHONPATH=src /venv/main/bin/python scripts/v6_rehearse_main_archival.py` exercises the complementary main path on temporary copies of an audited real60-QA readiness arm plus its separate60-QA warmup. Ten raw files include both gateway ledgers. It re-runs measured/warm integrity and official measured quality, then compares exact bytes, full quality JSON, fairness, completion/decode, native histogram, per-request additive waits and sampled resources before/after archive expansion. The existing subset audit's raw SHA and derived fairness/decode/histogram evidence are checked first; original raw/setup artifacts are verified unchanged afterwards. `results/v3/v6_main_archival_rehearsal.json` records the proof and source/implementation hashes. No new inference or original-file compression/removal occurs, and the rehearsal is not full1986QA/48GB validation.

The prospective full source list also explicitly includes the existing metric sampler/summary, gateway extraction, model selection, service PID helper and main start/reset/preflight scripts, plus the admission reconstruction used by fairness/native integrity. Their implementations remain unchanged; the expanded seal binds these helper identities before any full freeze.


`PYTHONPATH=src /venv/main/bin/python scripts/v6_analyze_main_resources.py` validates the retained24-arm main resource supplement without contacting serving endpoints. It checks original request SHA, measured collector/summary source identities, strict counter reconciliation and sample windows bracketing all1,440responses, then writes raw/setup/source fingerprints and all per-run/aggregate samples to `v6dev1_main_resources.json`. GPU utilization/power/board-energy estimates are approximately1Hz sampled-window descriptors; CPU tree deltas, separate chooser CPU, clocks/temperature and missing instrumentation keep distinct scopes. This is not a full benchmark, exact kernel/energy trace or a causal cross-engine comparison.


Before full freeze, `tests/test_v6_full_flow.py` fault injection reproduced a cleanup defect: a failed gateway-stop command left other services untouched and skipped config restoration. The full controller now attempts all stops and restores original config in a nested finally block while surfacing failures. The failed arm remains unarchived/ineligible; it never advances to another arm. This is CPU-only control-flow verification, not an observed GPU failure or liveness fix. Existing registered main-controls actors remain unchanged.


The main low-reuse subset is now complete in `v6controls1_main_lowreuse_subset_audit.json` / `_quality.json` / `_waits.json`: nine fresh engine/LMCache arms,72measured successes,540separate warmups, all three seeds pass the existing5% p95 gate for old union and readiness versus FIFO. Source-labelled CPU consumption0, compute190916, outputs/scores identical within each seed. Eight distinct QA are reused; no broad quality/tail guarantee. The full freezer still requires the complete36-arm stage and remaining GPU-fit/abstention controls; do not promote this subset to a complete prerequisite audit.


The main GPU-fit subset now passes all nine arms/540measured responses plus540separate warmups (`v6controls1_main_gpufit_subset_audit.json`, `_quality.json`, `_waits.json`). Every arm computes65122tokens, consumes0engine-labelled CPU-source tokens, records0preemptions and has valid native ITL coverage. Old union has identical outputs/scores to FIFO; readiness increases median7–9%, changes outputs and has mixed p95/F1 changes with no observed work saving. Keep this separate from native GPU-fit and the full10GiB larger-cache control. The complete main36-arm audit and abstention are still pending; these subsets cannot replace the full prerequisite.


The final full auditor now independently checks both process layers:30distinct positive engine PIDs and12distinct positive main LMCache PIDs, with native LMCache IDs absent. A reused/missing CPU-tier PID rejects the stage even if all engine PIDs differ. Projected-ledger CPU tests cover this condition along with invalid IDs, incomplete graphs and reused engines; these tests are not actual48GB/full GPU evidence. The prospective analysis seal already covers the final auditor, and namespace copies retain the same check automatically.


The terminal main24 audit uses a legacy schema without a `complete` flag. The freezer's prerequisite validator explicitly supports that named artifact only when its terminal scope,24unique IDs/1440summed requests and zero errors match. Modern native/main-controls audits still need explicit `complete=true`; partial, duplicate, miscounted or failed artifacts reject. Regression tests use the real completed main/native files without rewriting them, plus clearly projected control fixtures. This corrects an incompatible strict check added before full launch and does not change the original GPU measurements or acceptance thresholds.


The main controls are now terminal:36arms1260/1260measured successes0errors plus2160separate warmups, with36fresh engine/LMCache units and native ITL coverage36/36. The automatic dependency produced `v6controls1_main_audit.json` / `_quality.json`; they are immutable prerequisites of the full seal. The separate abstention subset scores7/12 for all9arms, no cap hits, answerableF1=null; it is12unique QA, not full446. `scripts/v6_plot_main_controls.py` requires the complete stage and renders inspected median/p95 contrasts plus plot/audit/source SHA provenance. `v5_analyze_waits.py` reconstructs all36gateway arms in `_main_waits.json`.

Full1,986-token parity and three-trace nonarrival identity preflight passed0mismatches. Seal `12f86b1a0698cbb56f3b290f53bb4cf660b38c6380bcece6e328a641228af366` was written22:07:24UTC; actor/helper31and analysis/evaluator17source hashes are now frozen. The controller is running, so do not start another engine, change sealed files/protocol, rerun seal-linked audits or overwrite results. The first main host heap capacity is observed48049946624bytes and its60-request warmup succeeded; no full measured arm is complete at this checkpoint. Native full payload is still expected/unobserved. Per-run official quality/integrity/archive and final30-arm reopening audit remain mandatory before final claims.
