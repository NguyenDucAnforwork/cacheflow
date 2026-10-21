# CacheFlow: reproducibility log

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

For every benchmark run, record: run ID, Git SHA, model/tokenizer revision, vLLM/LMCache versions, server and policy configs, corpus hash, trace seed, warm/cold reset method, arrival schedule hash, metric snapshot paths, and raw output paths. Exact launch and replay commands will be added after smoke verification. Never substitute untested commands for reproducible ones.

## Pinned setup and verified B1 smoke

Exact Python environment: `/venv/main/bin/python` 3.12.15, PyTorch 2.11.0+cu128. Model: `Qwen/Qwen3-1.7B` revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`. Initial root disk had 20 GiB free; check `df -h /workspace` before repeats.

Installation used `uv pip install --index-strategy unsafe-best-match --python /venv/main/bin/python 'vllm==0.22.0' 'lmcache==0.5.3' 'transformers==5.6.2' 'torch==2.11.0+cu128' 'torchaudio==2.11.0+cu128' 'torchvision==0.26.0+cu128' --extra-index-url https://download.pytorch.org/whl/cu128` with `UV_CACHE_DIR=/workspace/.uv-cache`. The CUDA 13 runtime library directory is prepended by `scripts/serve_vllm.sh` and `scripts/serve_lmcache.sh`.

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
