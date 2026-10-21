# CacheFlow: reproducibility log

Status: setup pending. Do not use these notes as a claim that vLLM, LMCache, or the model is installed.

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
