#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
trace=data/processed/v3/dev3-qps2-s101.jsonl
for arm in fifo:16 fifo:4 lpm_hint:4 lpm_hint:1 bundle_wave:4 fifo:1; do
    policy=${arm%:*};cap=${arm#*:}
    id="v3-screen-${policy}${cap}-dev3-qps2-s101"
    echo "$(date -u +%FT%TZ) START $id"
    bash scripts/v3_gateway.sh "$cap" "$policy"
    bash scripts/v2_reset.sh
    bash scripts/v3_run.sh "$id" "$trace"
    echo "$(date -u +%FT%TZ) DONE $id"
done
