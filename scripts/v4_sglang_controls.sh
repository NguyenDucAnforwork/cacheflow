#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
start_native() {
    local cap=$1 budget=$2
    /venv/main/bin/python scripts/v3_sglang_runtime.py configure --model qwen3-4b --gpu-kv-gib "$budget" \
        --attention-backend flashinfer --io-backend direct --max-running-requests "$cap"
    supervisorctl start cacheflow_v3_sglang
    for ((i=0;i<180;i++));do
        if curl --silent --fail --max-time 2 http://127.0.0.1:8300/health >/dev/null;then return 0;fi
        sleep 2
    done
    return 1
}
configure_gateway() {
    /venv/main/bin/python scripts/v3_runtime.py configure --model qwen3-4b --max-inflight 16 \
        --max-num-seqs 16 --cuda-graphs --kv-capacity-tokens "$1" --upstream http://127.0.0.1:8300 \
        --policy packing_reuse --max-bypasses 8
    supervisorctl start cacheflow_v2_gateway
    for ((i=0;i<60;i++));do
        if curl --silent --fail --max-time 2 http://127.0.0.1:8100/health >/dev/null;then return 0;fi
        sleep 1
    done
    return 1
}
paired() {
    local namespace=$1 seed=$2 trace=$3
    local arms=(native q8)
    if [[ "$seed" == 102 ]];then arms=(q8 native);fi
    for arm in "${arms[@]}";do
        local extra=()
        if [[ "$arm" == q8 ]];then extra=(--replay-url http://127.0.0.1:8100 --gateway-policy packing_reuse);fi
        PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
            "${namespace}-${arm}-s${seed}" "$trace" "${extra[@]}"
    done
}
# Precondition: cap/profile diagnostic is terminal and both services stopped.
start_native 4 6
configure_gateway 43664
PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
    v4-sgcontrol-cap4-warm-s101 data/processed/v3/v4-dev4b3-qps4-s101.jsonl
for seed in 101 102 103;do
    paired v4-sgcontrol-cap4 "$seed" "data/processed/v3/v4-dev4b3-qps4-s${seed}.jsonl"
done
supervisorctl stop cacheflow_v3_sglang cacheflow_v2_gateway
start_native 16 6
configure_gateway 43664
PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
    v4-sgcontrol-lowreuse-warm-s101 data/processed/v3/v4-lowreuse8-qps4-s101.jsonl
PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
    v4-sgcontrol-qps2-warm-s101 data/processed/v3/v4-dev4b3-qps2-s101.jsonl
for seed in 101 102 103;do
    paired v4-sgcontrol-lowreuse "$seed" "data/processed/v3/v4-lowreuse8-qps4-s${seed}.jsonl"
    paired v4-sgcontrol-qps2 "$seed" "data/processed/v3/v4-dev4b3-qps2-s${seed}.jsonl"
done
supervisorctl stop cacheflow_v3_sglang cacheflow_v2_gateway
start_native 16 10
configure_gateway 72800
PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
    v4-sgcontrol-gpufit-warm-s101 data/processed/v3/v4-dev4b3-qps4-s101.jsonl
for seed in 101 102 103;do
    paired v4-sgcontrol-gpufit "$seed" "data/processed/v3/v4-dev4b3-qps4-s${seed}.jsonl"
done
supervisorctl stop cacheflow_v3_sglang cacheflow_v2_gateway
