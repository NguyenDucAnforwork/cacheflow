#!/usr/bin/env bash
set -euo pipefail

root=${CACHEFLOW_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
venv=${CACHEFLOW_VENV:-/venv/main}
source "$venv/bin/activate" >/dev/null
export HF_HOME=${HF_HOME:-/workspace/.hf_home}
export VLLM_SERVER_DEV_MODE=1
cu13_lib="$venv/lib/python3.12/site-packages/nvidia/cu13/lib"
if [[ -d "$cu13_lib" ]]; then
    export LD_LIBRARY_PATH="$cu13_lib:${LD_LIBRARY_PATH:-}"
fi

model=${CACHEFLOW_MODEL_PATH:-$HF_HOME/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e}
mode=${CACHEFLOW_MODE:-$(cat "$root/.cacheflow-mode" 2>/dev/null || printf B1)}
gpu_kv_bytes=${CACHEFLOW_GPU_KV_BYTES:-$(cat "$root/.cacheflow-v2-gpu-kv-bytes" 2>/dev/null || printf 8589934592)}
max_model_len=${CACHEFLOW_MAX_MODEL_LEN:-32768}
max_num_seqs=${CACHEFLOW_MAX_NUM_SEQS:-4}
[[ -d "$model" ]] || { echo "missing pinned model: $model" >&2; exit 2; }
case "$gpu_kv_bytes" in
    4294967296|6442450944|8589934592) ;;
    *) echo "unsupported GPU KV budget: $gpu_kv_bytes" >&2; exit 2 ;;
esac

args=(
    "$model" --served-model-name cacheflow-qwen3-1.7b
    --host 127.0.0.1 --port 8000 --dtype bfloat16
    --max-model-len "$max_model_len" --max-num-seqs "$max_num_seqs"
    --kv-cache-memory-bytes "$gpu_kv_bytes"
    --generation-config vllm --enable-prefix-caching
)
if [[ -s "$root/.cacheflow-v3-runtime.json" ]]; then
    export PYTHONHASHSEED=0
    export VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=0
    "$venv/bin/python" "$root/scripts/v3_runtime.py" validate >/dev/null
    mapfile -t v3_args < <("$venv/bin/python" "$root/scripts/v3_runtime.py" vllm-args)
    args+=("${v3_args[@]}")
else
    args+=(--enforce-eager)
fi
case "$mode" in
    B1) ;;
    B2|B3)
        args+=(--kv-transfer-config '{"kv_connector":"LMCacheMPConnector","kv_connector_module_path":"lmcache.integration.vllm.lmcache_mp_connector","kv_role":"kv_both","kv_connector_extra_config":{"lmcache.mp.host":"127.0.0.1","lmcache.mp.port":5555}}')
        ;;
    *) echo "unknown V2 mode: $mode" >&2; exit 2 ;;
esac
exec vllm serve "${args[@]}"
