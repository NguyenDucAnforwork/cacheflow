#!/usr/bin/env bash
set -euo pipefail
root=${CACHEFLOW_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
export HF_HOME=/workspace/.hf_home
export LD_LIBRARY_PATH="/venv/main/lib/python3.12/site-packages/nvidia/cu13/lib:${LD_LIBRARY_PATH:-}"
export PYTHONHASHSEED=0
export SGLANG_SKIP_WARMUP=0
args=(--model-path /workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e
 --served-model-name cacheflow-qwen3-1.7b --host 127.0.0.1 --port 8300 --dtype bfloat16
 --context-length 32768 --max-total-tokens 37440 --max-running-requests 16 --random-seed 0
 --chunked-prefill-size 8192 --page-size 16 --mem-fraction-static 0.8
 --enable-hierarchical-cache --hicache-size 16 --hicache-write-policy write_through
 --hicache-io-backend kernel --hicache-mem-layout page_first --schedule-policy lpm
 --enable-metrics --attention-backend triton)
/venv/sglang-baseline/bin/python -m sglang.launch_server "${args[@]}" 2>&1 | tee "$root/results/v3/sglang_server.log"
