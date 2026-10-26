#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
# Configured by v3_runtime: max_num_seqs16 / batch8192 / CUDA graphs / byte KV events.
for arm in fifo:16 fifo:4 lpm_real:4 packing_fifo:4 residency:4 bundle_wave:4; do
    policy=${arm%:*};cap=${arm#*:}
    id="v3-tuned16-${policy}${cap}-dev3-qps2-s101"
    bash scripts/v3_gateway.sh "$cap" "$policy"
    bash scripts/v2_reset.sh
    bash scripts/v3_run.sh "$id" data/processed/v3/dev3-qps2-s101.jsonl
 done
