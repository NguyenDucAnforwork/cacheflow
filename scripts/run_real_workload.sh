#!/usr/bin/env bash
# usage: run_real_workload.sh "CONFIG LOAD TAG" ...
#   CONFIG: B1 | B1T | B2 | B2M | B2T | B2TP
#           B1* = GPU prefix cache only, B2* = GPU + CPU tier; max_num_batched_tokens is passed explicitly:
#           2048 (no suffix), 4096 (M), 8192 (T); P = gateway policy class_first (chat admitted first),
#           A = gateway policy class_aged (chat first, but a request waiting >= age cap counts as chat), otherwise fifo
#   LOAD:   moderate | medium | mid65 | mid50 | mid45 | burst
#   D = gateway policy class_demote (chat first; docs that cannot meet their SLO are served last)
#   W = wide gateway (64 in-flight) without engine priority (controls: B2TW FIFO, B2TPW gateway chat-first)
#   V24/V32, P24/P32 = engine priority / gateway chat-first with 24 or 32 in-flight at the gateway (width sweep)
#   VD4 = same with 4 documents in flight (attempt 2, binding cap)
#   VS4 = engine priority with vLLM max_num_seqs 4 (queue stays in the engine); VF4 = engine priority, documents capped at 4 at the gateway, FIFO (policy engine_cap)
#   VD = engine priority for chat + gateway demotion for documents (policy engine_demote, 16 documents in flight, chat bypasses the cap)
#   V = engine-level priority (vLLM --scheduling-policy priority, request priority chat 0 / doc 1, gateway pass-through with 64 in-flight)
#   S = gateway policy class_slack (chat first; a doc is promoted once its remaining slack is below its expected service time + margin)
# env: TRACE_PREFIX (default real), RUN_PREFIX (default real), REGISTRY (default results/real_registry.csv)
# Each run is a full cold restart (set_mode.sh) followed by two identical tiny warm-up requests; no cache carry-over.
set -euo pipefail
cd /workspace
for spec in "$@"; do
    read -r config trace tag <<< "$spec"
    policy=fifo
    engine_priority=0
    wide=0
    width=0
    seqs=0
    case "$config" in
        B1) mode=B1; mnbt=2048 ;;
        B1T) mode=B1; mnbt=8192 ;;
        B2) mode=B2; mnbt=2048 ;;
        B2M) mode=B2; mnbt=4096 ;;
        B2T) mode=B2; mnbt=8192 ;;
        B2TP) mode=B2; mnbt=8192; policy=class_first ;;
        B2TA) mode=B2; mnbt=8192; policy=class_aged ;;
        B2TS) mode=B2; mnbt=8192; policy=class_slack ;;
        B2TD) mode=B2; mnbt=8192; policy=class_demote ;;
        B2TV) mode=B2; mnbt=8192; engine_priority=1 ;;
        B2TVD8) mode=B2; mnbt=8192; policy=engine_demote; engine_priority=1; width=8 ;;
        B2TVD12) mode=B2; mnbt=8192; policy=engine_demote; engine_priority=1; width=12 ;;
        B2TVS4) mode=B2; mnbt=8192; engine_priority=1; wide=1; seqs=4 ;;
        B2TVF4) mode=B2; mnbt=8192; policy=engine_cap; engine_priority=1; width=4 ;;
        B2TVD4) mode=B2; mnbt=8192; policy=engine_demote; engine_priority=1; width=4 ;;
        B2TVD) mode=B2; mnbt=8192; policy=engine_demote; engine_priority=1; width=16 ;;
        B2TV24) mode=B2; mnbt=8192; engine_priority=1; width=24 ;;
        B2TV32) mode=B2; mnbt=8192; engine_priority=1; width=32 ;;
        B2TP24) mode=B2; mnbt=8192; policy=class_first; width=24 ;;
        B2TP32) mode=B2; mnbt=8192; policy=class_first; width=32 ;;
        B2TW) mode=B2; mnbt=8192; wide=1 ;;
        B2TPW) mode=B2; mnbt=8192; policy=class_first; wide=1 ;;
        *) echo "unknown config $config" >&2; exit 2 ;;
    esac
    run_id="${RUN_PREFIX:-real}-${trace}-$(echo "$config" | tr 'A-Z' 'a-z')-${tag}"
    printf '%s\n' "$mnbt" > /workspace/.cacheflow-mnbt
    rm -f /workspace/.cacheflow-sched-policy /workspace/.cacheflow-max-inflight /workspace/.cacheflow-max-num-seqs
    if [[ "$seqs" -gt 0 ]]; then
        printf '%s\n' "$seqs" > /workspace/.cacheflow-max-num-seqs
    fi
    if [[ "$engine_priority" == 1 ]]; then
        printf 'priority\n' > /workspace/.cacheflow-sched-policy
    fi
    if [[ "$width" -gt 0 ]]; then
        printf '%s\n' "$width" > /workspace/.cacheflow-max-inflight
    elif [[ "$engine_priority" == 1 || "$wide" == 1 ]]; then
        printf '64\n' > /workspace/.cacheflow-max-inflight
    fi
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
rm -f /workspace/.cacheflow-mnbt /workspace/.cacheflow-age-cap-ms /workspace/.cacheflow-sched-policy /workspace/.cacheflow-max-inflight /workspace/.cacheflow-max-num-seqs
