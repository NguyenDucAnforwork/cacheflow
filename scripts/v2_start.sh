#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mode=${1:?usage: v2_start.sh B1|B2|B3 [fifo|dhas] [gpu_kv_gib]}
policy=${2:-fifo}
gpu_kv_gib=${3:-8}
case "$mode:$policy" in
    B1:fifo|B2:fifo|B3:dhas) ;;
    *) echo "invalid V2 mode/policy: $mode/$policy" >&2; exit 2 ;;
esac
case "$gpu_kv_gib" in
    4|6|8) ;;
    10) [[ -s "$root/.cacheflow-v3-runtime.json" ]] || exit 2 ;;
    *) echo "GPU KV budget must be 4, 6 or 8 GiB" >&2; exit 2 ;;
esac
venv=${CACHEFLOW_VENV:-/venv/main}
"$venv/bin/python" "$root/scripts/v2_preflight.py"
supervisorctl stop cacheflow_v2_gateway cacheflow_v2_vllm cacheflow_v2_lmcache >/dev/null 2>&1 || true
printf '%s\n' "$mode" > "$root/.cacheflow-mode"
printf '%s\n' "$policy" > "$root/.cacheflow-policy"
printf '%s\n' "$((gpu_kv_gib * 1024 * 1024 * 1024))" > "$root/.cacheflow-v2-gpu-kv-bytes"

wait_for_url() {
    local url=$1
    local attempts=$2
    for ((i=0; i<attempts; i++)); do
        curl --silent --fail --max-time 2 "$url" >/dev/null && return 0
        sleep 2
    done
    echo "health endpoint did not become ready: $url" >&2
    return 1
}

if [[ "$mode" != B1 ]]; then
    supervisorctl start cacheflow_v2_lmcache
    wait_for_url http://127.0.0.1:18080/metrics 60
fi
supervisorctl start cacheflow_v2_vllm
wait_for_url http://127.0.0.1:8000/health 180
supervisorctl start cacheflow_v2_gateway
wait_for_url http://127.0.0.1:8100/health 60
supervisorctl status cacheflow_v2_vllm cacheflow_v2_gateway
