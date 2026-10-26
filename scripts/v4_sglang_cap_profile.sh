#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
wait_native() {
    for ((i=0;i<180;i++)); do
        if curl --silent --fail --max-time 2 http://127.0.0.1:8300/health >/dev/null;then return 0;fi
        sleep 2
    done
    return 1
}
for cap in 1 4;do
    supervisorctl stop cacheflow_v3_sglang
    /venv/main/bin/python scripts/v3_sglang_runtime.py configure --model qwen3-4b --gpu-kv-gib 6 \
        --attention-backend flashinfer --io-backend direct --max-running-requests "$cap"
    supervisorctl start cacheflow_v3_sglang
    wait_native
    for phase in warm measured;do
        PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
            "v4-sgcap-direct-lpm${cap}-${phase}-s101" data/processed/v3/v4-dev4b3-qps4-s101.jsonl
    done
done
supervisorctl stop cacheflow_v3_sglang
/venv/main/bin/python scripts/v3_sglang_runtime.py configure --model qwen3-4b --gpu-kv-gib 6 \
    --attention-backend flashinfer --io-backend kernel --max-running-requests 16 --profile-transfers
supervisorctl start cacheflow_v3_sglang
wait_native
PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
    v4-sgdiag-admission-native-s101 data/processed/v3/v4-dev4b3-qps4-s101.jsonl
/venv/main/bin/python scripts/v3_runtime.py gateway --policy packing_reuse --max-inflight 16 --max-bypasses 8
bash scripts/v3_gateway.sh 16 packing_reuse
PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
    v4-sgdiag-admission-q8-s101 data/processed/v3/v4-dev4b3-qps4-s101.jsonl \
    --replay-url http://127.0.0.1:8100 --gateway-policy packing_reuse
supervisorctl stop cacheflow_v3_sglang cacheflow_v2_gateway
