#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
# Same optimized policy and engine, explicit local connection-pool comparison.
for keepalive in 128 0; do
    /venv/main/bin/python scripts/v3_runtime.py gateway --max-inflight 16 --policy packing_fifo --keepalive-connections "$keepalive"
    bash scripts/v3_gateway.sh 16 packing_fifo
    bash scripts/v2_reset.sh
    CACHEFLOW_ALLOW_FAILED_DIAGNOSTIC=1 bash scripts/v3_run.sh \
        "v3-netdiag-keepalive${keepalive}-packing16-qps4-s101" data/processed/v3/dev4b3-qps4-s101.jsonl
 done
