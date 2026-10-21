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
