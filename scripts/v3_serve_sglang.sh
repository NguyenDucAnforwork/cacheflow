#!/usr/bin/env bash
set -euo pipefail
root=${CACHEFLOW_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
export HF_HOME=/workspace/.hf_home
export LD_LIBRARY_PATH="/venv/main/lib/python3.12/site-packages/nvidia/cu13/lib:${LD_LIBRARY_PATH:-}"
export PYTHONHASHSEED=0
export SGLANG_SKIP_WARMUP=0
export IN_BATCH_PREFIX_CACHING_CHECK_THRESHOLD=$(/venv/main/bin/python -c 'import json,sys;print(json.loads(sys.argv[1])["inbatch_check_threshold"])' "$(/venv/main/bin/python "$root/scripts/v3_sglang_runtime.py" validate)")
export IN_BATCH_PREFIX_CACHING_DEPRIORITIZE_THRESHOLD=$(/venv/main/bin/python -c 'import json,sys;print(json.loads(sys.argv[1])["inbatch_deprioritize_threshold"])' "$(/venv/main/bin/python "$root/scripts/v3_sglang_runtime.py" validate)")
/venv/main/bin/python "$root/scripts/v3_sglang_runtime.py" validate >/dev/null
if /venv/main/bin/python -c 'import json,sys;sys.exit(not json.loads(sys.argv[1]).get("profile_transfers"))' "$(/venv/main/bin/python "$root/scripts/v3_sglang_runtime.py" validate)"; then
    export CACHEFLOW_SGLANG_TRANSFER_PROFILE=1
    export CACHEFLOW_SGLANG_TRANSFER_LOG="$root/results/v3/raw/sglang_transfer_events.jsonl"
    export PYTHONPATH="$root/scripts/sglang_profile_hooks:$root/src${PYTHONPATH:+:$PYTHONPATH}"
fi
if /venv/main/bin/python -c 'import json,sys;sys.exit(not json.loads(sys.argv[1]).get("same_batch_guard"))' "$(/venv/main/bin/python "$root/scripts/v3_sglang_runtime.py" validate)"; then
    export CACHEFLOW_SG_SAME_BATCH_GUARD=1
    export PYTHONPATH="$root/scripts/sglang_profile_hooks:$root/src${PYTHONPATH:+:$PYTHONPATH}"
fi
mapfile -t args < <(/venv/main/bin/python "$root/scripts/v3_sglang_runtime.py" args)
mkdir -p "$root/results/v3/raw/sglang_servers"
if [[ -s "$root/results/v3/sglang_server.log" ]]; then
    mv "$root/results/v3/sglang_server.log" "$root/results/v3/raw/sglang_servers/$(date -u +%Y%m%dT%H%M%S)-$$.log"
fi
/venv/sglang-baseline/bin/python -m sglang.launch_server "${args[@]}" 2>&1 | tee "$root/results/v3/sglang_server.log"
