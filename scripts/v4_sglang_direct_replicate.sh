#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
# Prospective dev replication; confirmation conversations remain untouched.
supervisorctl stop cacheflow_v3_sglang
/venv/main/bin/python scripts/v3_sglang_runtime.py configure --model qwen3-4b --gpu-kv-gib 6 \
    --attention-backend flashinfer --io-backend direct --max-running-requests 16
supervisorctl start cacheflow_v3_sglang
ready=0
for ((i=0;i<180;i++)); do
    if curl --silent --fail --max-time 2 http://127.0.0.1:8300/health >/dev/null;then ready=1;break;fi
    sleep 2
done
[[ "$ready" == 1 ]]
PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
    v4-sgdirect-repl-warm-s101 data/processed/v3/v4-dev4b3-qps4-s101.jsonl
for seed in 101 102 103; do
    case "$seed" in
        101) arms=(native q4 q8) ;;
        102) arms=(q8 q4 native) ;;
        103) arms=(q4 native q8) ;;
    esac
    for arm in "${arms[@]}";do
        extra=()
        if [[ "$arm" != native ]];then
            /venv/main/bin/python scripts/v3_runtime.py gateway --policy packing_reuse --max-inflight 16 --max-bypasses "${arm#q}"
            bash scripts/v3_gateway.sh 16 packing_reuse
            extra=(--replay-url http://127.0.0.1:8100 --gateway-policy packing_reuse)
        fi
        PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
            "v4-sgdirect-repl-${arm}-s${seed}" "data/processed/v3/v4-dev4b3-qps4-s${seed}.jsonl" "${extra[@]}"
    done
done
