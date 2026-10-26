#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
# Diagnostic showed repeated partial prefixes above1024; test native tuning first.
# Run only after all other GPU jobs are terminal and the native service is stopped.
for cap in 4 16;do
    /venv/main/bin/python scripts/v3_sglang_runtime.py configure --model qwen3-4b --gpu-kv-gib 6 \
        --attention-backend flashinfer --io-backend direct --max-running-requests "$cap" \
        --inbatch-check-threshold 32768 --inbatch-deprioritize-threshold 1024
    supervisorctl start cacheflow_v3_sglang
    ready=0
    for ((i=0;i<180;i++));do
        if curl --silent --fail --max-time 2 http://127.0.0.1:8300/health >/dev/null;then ready=1;break;fi
        sleep 2
    done
    [[ "$ready" == 1 ]]
    for phase in warm measured;do
        PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
            "v4-sginbatch32768-direct-lpm${cap}-${phase}-s101" data/processed/v3/v4-dev4b3-qps4-s101.jsonl
    done
    supervisorctl stop cacheflow_v3_sglang
done
