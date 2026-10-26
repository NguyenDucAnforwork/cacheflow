#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
for policy in fifo lpm_real packing_fifo residency bundle_wave; do
    id="v3-bytes-${policy}4-dev3-qps2-s101"
    bash scripts/v3_gateway.sh 4 "$policy"
    bash scripts/v2_reset.sh
    bash scripts/v3_run.sh "$id" data/processed/v3/dev3-qps2-s101.jsonl
 done
