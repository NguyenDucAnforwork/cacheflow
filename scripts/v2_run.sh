#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
run_id=${1:?usage: v2_run.sh RUN_ID TRACE_JSONL [URL]}
trace=${2:?missing trace JSONL}
url=${3:-http://127.0.0.1:8100}
[[ "$run_id" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid run ID" >&2; exit 2; }
[[ -f "$trace" ]] || { echo "missing trace: $trace" >&2; exit 2; }
venv=${CACHEFLOW_VENV:-/venv/main}
source "$venv/bin/activate" >/dev/null
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
raw_dir="$root/results/v2/raw"
mkdir -p "$raw_dir"
raw="$raw_dir/$run_id.jsonl"
metrics="$raw_dir/$run_id.metrics.jsonl"
gateway_raw="$raw_dir/$run_id.gateway.jsonl"
[[ ! -e "$raw" && ! -e "$metrics" && ! -e "$gateway_raw" ]] || { echo "run artifacts already exist: $run_id" >&2; exit 2; }
curl --silent --fail --max-time 5 http://127.0.0.1:8000/health >/dev/null
if [[ "$url" == *:8100 ]]; then
    curl --silent --fail --max-time 5 http://127.0.0.1:8100/health >/dev/null
fi
for marker in .cacheflow-mode .cacheflow-policy .cacheflow-v2-gpu-kv-bytes; do
    [[ -s "$root/$marker" ]] || { echo "missing run configuration: $marker" >&2; exit 2; }
done
mode=$(cat "$root/.cacheflow-mode")
policy=$(cat "$root/.cacheflow-policy")
gpu_kv_bytes=$(cat "$root/.cacheflow-v2-gpu-kv-bytes")
engine_pid=$(supervisorctl pid cacheflow_v2_vllm)
[[ "$engine_pid" =~ ^[1-9][0-9]*$ ]] || { echo "vLLM PID unavailable" >&2; exit 1; }
replay_args=(--engine-pid "$engine_pid")
case "${CACHEFLOW_CAPTURE_TEXT:-0}" in
    1) replay_args+=(--capture-text) ;;
    0) ;;
    *) echo "CACHEFLOW_CAPTURE_TEXT must be 0 or 1" >&2; exit 2 ;;
esac
if [[ "$mode" != B1 ]]; then
    lmcache_pid=$(supervisorctl pid cacheflow_v2_lmcache)
    [[ "$lmcache_pid" =~ ^[1-9][0-9]*$ ]] || { echo "LMCache PID unavailable" >&2; exit 1; }
    replay_args+=(--lmcache-pid "$lmcache_pid")
fi
if [[ "$url" == *:8100 ]]; then
    replay_args+=(--gateway-trace-path "$gateway_raw")
fi
python -m cacheflow.collect_metrics --output "$metrics" &
collector=$!
cleanup() {
    kill -TERM "$collector" 2>/dev/null || true
    wait "$collector" 2>/dev/null || true
}
trap cleanup EXIT
for ((i=0; i<50; i++)); do
    [[ -s "$metrics" ]] && break
    kill -0 "$collector" 2>/dev/null || { echo "metric collector exited" >&2; exit 1; }
    sleep 0.1
done
[[ -s "$metrics" ]] || { echo "no baseline metric sample" >&2; exit 1; }
python -m cacheflow.v2_replay --trace "$trace" --url "$url" \
    --run-id "$run_id" --output "$raw" --registry "$root/results/v2/registry.csv" \
    --metrics-path "$metrics" --mode "$mode" --policy "$policy" \
    --gpu-kv-bytes "$gpu_kv_bytes" "${replay_args[@]}"
sleep 2
cleanup
trap - EXIT
if [[ "$url" == *:8100 ]]; then
    python "$root/scripts/v2_extract_gateway.py" \
        --gateway-log "$raw_dir/gateway.jsonl" --request-log "$raw" \
        --run-id "$run_id" --output "$gateway_raw" || {
            printf "gateway trace missing or mismatched\n" > "$root/results/v2/$run_id.invalid"
            exit 1
        }
fi
if [[ $(supervisorctl pid cacheflow_v2_vllm) != "$engine_pid" ]] || \
   { [[ "$mode" != B1 ]] && [[ $(supervisorctl pid cacheflow_v2_lmcache) != "$lmcache_pid" ]]; }; then
    printf "serving PID changed during run\n" > "$root/results/v2/$run_id.invalid"
    echo "serving PID changed; run invalid" >&2
    exit 1
fi
python -m cacheflow.v2_metrics "$metrics" \
    --output "$root/results/v2/$run_id.metrics_summary.json"
