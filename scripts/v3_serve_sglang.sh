#!/usr/bin/env bash
set -euo pipefail
root=${CACHEFLOW_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
export HF_HOME=/workspace/.hf_home
export LD_LIBRARY_PATH="/venv/main/lib/python3.12/site-packages/nvidia/cu13/lib:${LD_LIBRARY_PATH:-}"
export PYTHONHASHSEED=0
export SGLANG_SKIP_WARMUP=0
/venv/main/bin/python "$root/scripts/v3_sglang_runtime.py" validate >/dev/null
if /venv/main/bin/python -c 'import json,sys;sys.exit(not json.loads(sys.argv[1]).get("profile_transfers"))' "$(/venv/main/bin/python "$root/scripts/v3_sglang_runtime.py" validate)"; then
    export CACHEFLOW_SGLANG_TRANSFER_PROFILE=1
    export CACHEFLOW_SGLANG_TRANSFER_LOG="$root/results/v3/raw/sglang_transfer_events.jsonl"
    export PYTHONPATH="$root/scripts/sglang_profile_hooks:$root/src${PYTHONPATH:+:$PYTHONPATH}"
fi
mapfile -t args < <(/venv/main/bin/python "$root/scripts/v3_sglang_runtime.py" args)
/venv/sglang-baseline/bin/python -m sglang.launch_server "${args[@]}" 2>&1 | tee "$root/results/v3/sglang_server.log"
