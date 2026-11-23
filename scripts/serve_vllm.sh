#!/usr/bin/env bash
set -eo pipefail

mode=${1:-$(cat /workspace/.cacheflow-mode 2>/dev/null || printf B2)}
if [[ -n ${PROC_NAME:-} ]]; then
    source /opt/supervisor-scripts/utils/logging.sh ""
fi
source /venv/main/bin/activate >/dev/null
export HF_HOME=/workspace/.hf_home
export VLLM_SERVER_DEV_MODE=1
export LD_LIBRARY_PATH="/venv/main/lib/python3.12/site-packages/nvidia/cu13/lib:${LD_LIBRARY_PATH:-}"
model=/workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e
gpu_kv_bytes=6442450944
if [[ -f /workspace/.cacheflow-gpu-kv-bytes ]]; then
    gpu_kv_bytes=$(cat /workspace/.cacheflow-gpu-kv-bytes)
fi
case "$gpu_kv_bytes" in
    4294967296|6442450944|8589934592) ;;
    *) echo "unsupported GPU KV budget: $gpu_kv_bytes" >&2; exit 2 ;;
esac

mnbt_args=()
if [[ -f /workspace/.cacheflow-mnbt ]]; then
    mnbt=$(cat /workspace/.cacheflow-mnbt)
    case "$mnbt" in
        2048|4096|8192) mnbt_args=(--max-num-batched-tokens "$mnbt") ;;
        *) echo "unsupported max_num_batched_tokens: $mnbt" >&2; exit 2 ;;
    esac
fi

sched_args=()
if [[ -f /workspace/.cacheflow-sched-policy ]]; then
    case "$(cat /workspace/.cacheflow-sched-policy)" in
        priority) sched_args=(--scheduling-policy priority) ;;
        *) echo "unsupported scheduling policy marker" >&2; exit 2 ;;
    esac
fi

args=(
    "$model" --served-model-name cacheflow-qwen3-1.7b
    --host 127.0.0.1 --port 8000 --dtype bfloat16
    --max-model-len 12288 --max-num-seqs 16
    --kv-cache-memory-bytes "$gpu_kv_bytes" --enforce-eager
    --generation-config vllm
    "${mnbt_args[@]}" "${sched_args[@]}"
)

case "$mode" in
    B0) args+=(--no-enable-prefix-caching) ;;
    B1) args+=(--enable-prefix-caching) ;;
    B2|B3|B4)
        args+=(--enable-prefix-caching)
        args+=(--kv-transfer-config '{"kv_connector":"LMCacheMPConnector","kv_connector_module_path":"lmcache.integration.vllm.lmcache_mp_connector","kv_role":"kv_both","kv_connector_extra_config":{"lmcache.mp.host":"127.0.0.1","lmcache.mp.port":5555}}')
        ;;
    *) echo "unknown mode: $mode" >&2; exit 2 ;;
esac

exec vllm serve "${args[@]}"
