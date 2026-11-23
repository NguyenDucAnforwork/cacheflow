#!/usr/bin/env bash
# usage: run_real_workload.sh "CONFIG LOAD TAG" ...
#   CONFIG: B1 | B1T | B2 | B2M | B2T | B2TP
#           B1* = GPU prefix cache only, B2* = GPU + CPU tier; max_num_batched_tokens is passed explicitly:
#           2048 (no suffix), 4096 (M), 8192 (T); P = gateway policy class_first (chat admitted first),
#           A = gateway policy class_aged (chat first, but a request waiting >= age cap counts as chat), otherwise fifo
#   LOAD:   moderate | medium | mid65 | mid50 | mid45 | burst
#   S = gateway policy class_slack (chat first; a doc is promoted once its remaining slack is below its expected service time + margin)
# env: TRACE_PREFIX (default real), RUN_PREFIX (default real), REGISTRY (default results/real_registry.csv)
# Each run is a full cold restart (set_mode.sh) followed by two identical tiny warm-up requests; no cache carry-over.
set -euo pipefail
cd /workspace
for spec in "$@"; do
    read -r config trace tag <<< "$spec"
    policy=fifo
    case "$config" in
        B1) mode=B1; mnbt=2048 ;;
        B1T) mode=B1; mnbt=8192 ;;
        B2) mode=B2; mnbt=2048 ;;
        B2M) mode=B2; mnbt=4096 ;;
        B2T) mode=B2; mnbt=8192 ;;
        B2TP) mode=B2; mnbt=8192; policy=class_first ;;
        B2TA) mode=B2; mnbt=8192; policy=class_aged ;;
        B2TS) mode=B2; mnbt=8192; policy=class_slack ;;
        *) echo "unknown config $config" >&2; exit 2 ;;
    esac
    run_id="${RUN_PREFIX:-real}-${trace}-$(echo "$config" | tr 'A-Z' 'a-z')-${tag}"
    printf '%s\n' "$mnbt" > /workspace/.cacheflow-mnbt
    printf '%s\n' "${AGE_CAP_MS:-1500}" > /workspace/.cacheflow-age-cap-ms
    echo "### $run_id mode=$mode mnbt=$mnbt policy=$policy start $(date +%T)"
    bash scripts/set_mode.sh "$mode" "$policy" > "/workspace/results/raw/${run_id}.setmode.log" 2>&1
    for i in 1 2; do
        curl --silent --show-error --fail --max-time 60 http://127.0.0.1:8000/v1/completions \
            -H 'content-type: application/json' \
            -d '{"model":"cacheflow-qwen3-1.7b","prompt":"Hello, how are you today?","max_tokens":4,"temperature":0}' > /dev/null
    done
    bash scripts/run_real_benchmark.sh "$run_id" "${TRACE_PREFIX:-real}_${trace}"
    echo "### $run_id done $(date +%T)"
done
supervisorctl stop cacheflow_gateway cacheflow_vllm cacheflow_lmcache >/dev/null 2>&1 || true
rm -f /workspace/.cacheflow-mnbt /workspace/.cacheflow-age-cap-ms
