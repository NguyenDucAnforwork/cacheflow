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

Run order was B0 r1 → B1 r1 → B2 r3 → B1 r2 → B2 r4. Each mode was reset before its run: `./scripts/set_mode.sh B0 fifo` or `B1 fifo` or `B2 fifo`, then `./scripts/run_benchmark.sh RUN_ID long_doc_revisit 8192 8 4 64`. `results/raw/*.summary.json` records exact run IDs, Git HEAD and common trace SHA. The first B0 attempt stopped after setup because `supervisorctl status` returned a nonzero code for intentionally stopped LMCache; it produced no benchmark rows. The B0/B1 launcher status check was repaired before the five successful runs, but the benchmark summaries still contain the preceding committed HEAD. The next commit includes the exact launcher fix; this does not alter the engine or gateway code paths used in the measurements.
