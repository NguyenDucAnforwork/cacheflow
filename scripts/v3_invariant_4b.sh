#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
/venv/main/bin/python scripts/v3_runtime.py configure --model qwen3-4b --residency-events \
    --max-inflight 16 --max-num-seqs 16 --cuda-graphs --kv-capacity-tokens 43664 --batch-invariant --kv-events
bash scripts/v2_start.sh B2 fifo 6
for policy in fifo packing; do
    bash scripts/v3_gateway.sh 16 "$policy"
    bash scripts/v2_reset.sh
    bash scripts/v3_run.sh "v3-invariant4b-${policy}16-kvprofile-qps4-s101" data/processed/v3/dev4b3-qps4-s101.jsonl
done
