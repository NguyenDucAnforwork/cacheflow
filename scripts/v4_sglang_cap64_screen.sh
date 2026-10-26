#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
for budget in 6 10;do
    capacity=43664
    if [[ "$budget" == 10 ]];then capacity=72800;fi
    /venv/main/bin/python scripts/v3_sglang_runtime.py configure --model qwen3-4b --gpu-kv-gib "$budget" \
        --attention-backend flashinfer --io-backend direct --max-running-requests 16
    supervisorctl start cacheflow_v3_sglang
    ready=0
    for ((i=0;i<180;i++));do
        if curl --silent --fail --max-time 2 http://127.0.0.1:8300/health >/dev/null;then ready=1;break;fi
        sleep 2
    done
    [[ "$ready" == 1 ]]
    /venv/main/bin/python scripts/v3_runtime.py configure --model qwen3-4b --max-inflight 64 \
        --max-num-seqs 16 --cuda-graphs --kv-capacity-tokens "$capacity" --upstream http://127.0.0.1:8300 \
        --policy packing_reuse --max-bypasses 8
    supervisorctl start cacheflow_v2_gateway
    ready=0
    for ((i=0;i<60;i++));do
        if curl --silent --fail --max-time 2 http://127.0.0.1:8100/health >/dev/null;then ready=1;break;fi
        sleep 1
    done
    [[ "$ready" == 1 ]]
    PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
        "v4-sgcap64-kv${budget}-warm-s101" data/processed/v3/v4-dev4b3-qps4-s101.jsonl
    arms=(native fifo-inline packing-inline packing-thread fifo-thread)
    if [[ "$budget" == 10 ]];then arms=(fifo-thread packing-thread packing-inline fifo-inline native);fi
    for arm in "${arms[@]}";do
        extra=()
        if [[ "$arm" != native ]];then
            policy=fifo
            if [[ "$arm" == packing-* ]];then policy=packing_reuse;fi
            flag=--no-prepare-in-thread
            if [[ "$arm" == *-thread ]];then flag=--prepare-in-thread;fi
            /venv/main/bin/python scripts/v3_runtime.py gateway --policy "$policy" --max-inflight 64 --max-bypasses 8 "$flag"
            extra=(--replay-url http://127.0.0.1:8100 --gateway-policy "$policy")
        fi
        PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
            "v4-sgcap64-kv${budget}-${arm}-s101" data/processed/v3/v4-dev4b3-qps4-s101.jsonl "${extra[@]}"
    done
    supervisorctl stop cacheflow_v3_sglang cacheflow_v2_gateway
done
