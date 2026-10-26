#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
plan=0
resume_controls=0
for option in "$@";do
    case "$option" in
        --plan) plan=1 ;;
        --resume-controls) resume_controls=1 ;;
        *) echo "unknown option: $option" >&2;exit 2 ;;
    esac
done
if [[ "$plan" == 0 ]];then [[ "$(supervisorctl pid cacheflow_v2_vllm)" == 0 ]];fi
benchmark() {
    if [[ "$plan" == 1 ]];then printf 'BENCH\t%s\t%s\n' "$1" "$2";return;fi
    PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py "$@"
}
stop_native() {
    if [[ "$plan" == 0 ]];then supervisorctl stop cacheflow_v3_sglang cacheflow_v2_gateway;fi
}
start_native() {
    local policy=$1 budget=$2
    if [[ "$plan" == 1 ]];then printf 'ENGINE\t%s\t%s\n' "$policy" "$budget";return;fi
    /venv/main/bin/python scripts/v3_sglang_runtime.py configure --model qwen3-4b --gpu-kv-gib "$budget" \
        --attention-backend flashinfer --io-backend direct --max-running-requests 16 \
        --schedule-policy "$policy" --same-batch-guard
    supervisorctl start cacheflow_v3_sglang
    for ((i=0;i<180;i++));do
        if curl --silent --fail --max-time 2 http://127.0.0.1:8300/health >/dev/null;then return 0;fi
        sleep 2
    done
    return 1
}
start_gateway() {
    if [[ "$plan" == 1 ]];then return;fi
    /venv/main/bin/python scripts/v3_runtime.py configure --model qwen3-4b --max-inflight 64 \
        --max-num-seqs 16 --cuda-graphs --kv-capacity-tokens "$1" --upstream http://127.0.0.1:8300 \
        --policy packing_reuse --max-bypasses 8 --prepare-in-thread
    supervisorctl start cacheflow_v2_gateway
    for ((i=0;i<60;i++));do
        if curl --silent --fail --max-time 2 http://127.0.0.1:8100/health >/dev/null;then return 0;fi
        sleep 1
    done
    return 1
}
run_arms() {
    local tag=$1 seed=$2 trace=$3 include_fifo=${4:-0}
    local arm policy
    local extra=()
    local arms=(native union)
    if [[ "$include_fifo" == 1 ]];then arms=(native fifo union);fi
    if [[ "$seed" == 102 ]];then
        arms=(union native)
        if [[ "$include_fifo" == 1 ]];then arms=(union fifo native);fi
    fi
    if [[ "$seed" == 103 && "$include_fifo" == 1 ]];then arms=(fifo native union);fi
    for arm in "${arms[@]}";do
        extra=()
        if [[ "$arm" != native ]];then
            policy=packing_reuse
            if [[ "$arm" == fifo ]];then policy=fifo;fi
            if [[ "$plan" == 0 ]];then
                /venv/main/bin/python scripts/v3_runtime.py gateway --policy "$policy" --max-inflight 64 --max-bypasses 8 --prepare-in-thread
            fi
            extra=(--replay-url http://127.0.0.1:8100 --gateway-policy "$policy")
        fi
        benchmark "v4-validate2-${tag}-${arm}-s${seed}" "$trace" "${extra[@]}"
    done
}
for policy in lpm dfs-weight;do
    start_native "$policy" 6
    start_gateway 43664
    benchmark "v4-validate2-${policy}-warm-s101" data/processed/v3/v4-dev4b3-qps4-s101.jsonl
    include_fifo=0
    if [[ "$policy" == lpm ]];then include_fifo=1;fi
    if [[ "$policy" != lpm || "$resume_controls" == 0 ]];then
        for seed in 101 102 103;do
            run_arms "${policy}-qps4" "$seed" "data/processed/v3/v4-dev4b3-qps4-s${seed}.jsonl" "$include_fifo"
        done
    fi
    if [[ "$policy" == lpm ]];then
        benchmark v4-validate2-lowreuse-warm-s101 data/processed/v3/v4-lowreuse8-qps4-s101.jsonl
        for seed in 101 102 103;do
            run_arms lowreuse "$seed" "data/processed/v3/v4-lowreuse8-qps4-s${seed}.jsonl"
            run_arms lpm-qps2 "$seed" "data/processed/v3/v4-dev4b3-qps2-s${seed}.jsonl"
        done
    fi
    stop_native
done
start_native lpm 10
start_gateway 72800
benchmark v4-validate2-gpufit-warm-s101 data/processed/v3/v4-dev4b3-qps4-s101.jsonl
for seed in 101 102 103;do
    run_arms gpufit "$seed" "data/processed/v3/v4-dev4b3-qps4-s${seed}.jsonl"
done
stop_native
