#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
/venv/main/bin/python scripts/v3_sglang_runtime.py configure --model qwen3-4b --gpu-kv-gib 6 \
    --attention-backend flashinfer --io-backend direct --max-running-requests 16 --same-batch-guard
supervisorctl start cacheflow_v3_sglang
ready=0
for ((i=0;i<180;i++));do
    if curl --silent --fail --max-time 2 http://127.0.0.1:8300/health >/dev/null;then ready=1;break;fi
    sleep 2
done
[[ "$ready" == 1 ]]
PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
    v4-sgguard-direct-warm-s101 data/processed/v3/v4-dev4b3-qps4-s101.jsonl
/venv/main/bin/python scripts/v3_runtime.py configure --model qwen3-4b --max-inflight 64 \
    --max-num-seqs 16 --cuda-graphs --kv-capacity-tokens 43664 --upstream http://127.0.0.1:8300 \
    --policy packing_reuse --max-bypasses 8 --prepare-in-thread
supervisorctl start cacheflow_v2_gateway
ready=0
for ((i=0;i<60;i++));do
    if curl --silent --fail --max-time 2 http://127.0.0.1:8100/health >/dev/null;then ready=1;break;fi
    sleep 1
done
[[ "$ready" == 1 ]]
for arm in native fifo packing_reuse;do
    extra=()
    if [[ "$arm" != native ]];then
        /venv/main/bin/python scripts/v3_runtime.py gateway --policy "$arm" --max-inflight 64 --max-bypasses 8 --prepare-in-thread
        extra=(--replay-url http://127.0.0.1:8100 --gateway-policy "$arm")
    fi
    PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
        "v4-sgguard-direct-${arm}-s101" data/processed/v3/v4-dev4b3-qps4-s101.jsonl "${extra[@]}"
done
supervisorctl stop cacheflow_v3_sglang cacheflow_v2_gateway
