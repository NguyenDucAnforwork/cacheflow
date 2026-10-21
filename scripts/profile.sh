#!/usr/bin/env bash
set -euo pipefail
cd /workspace

supervisorctl start cacheflow_otlp
touch /workspace/.cacheflow-trace
cleanup() {
    supervisorctl stop cacheflow_gateway cacheflow_vllm cacheflow_lmcache 2>/dev/null || true
    sleep 5  # permit the OTLP batch exporter to flush after LMCache exits
    supervisorctl stop cacheflow_otlp 2>/dev/null || true
    rm -f /workspace/.cacheflow-trace
}
trap cleanup EXIT

./scripts/set_mode.sh B2 fifo
./scripts/run_benchmark.sh b2-profile-8k-r1 long_doc_revisit 8192 8 4 64
