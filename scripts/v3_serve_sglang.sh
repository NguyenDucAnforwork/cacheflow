#!/usr/bin/env bash
set -euo pipefail
root=${CACHEFLOW_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
export HF_HOME=/workspace/.hf_home
export LD_LIBRARY_PATH="/venv/main/lib/python3.12/site-packages/nvidia/cu13/lib:${LD_LIBRARY_PATH:-}"
export PYTHONHASHSEED=0
export SGLANG_SKIP_WARMUP=0
/venv/main/bin/python "$root/scripts/v3_sglang_runtime.py" validate >/dev/null
mapfile -t args < <(/venv/main/bin/python "$root/scripts/v3_sglang_runtime.py" args)
/venv/sglang-baseline/bin/python -m sglang.launch_server "${args[@]}" 2>&1 | tee "$root/results/v3/sglang_server.log"
