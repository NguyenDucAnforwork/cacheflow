#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
/venv/main/bin/python - <<'PY'
import json
c=json.load(open('.cacheflow-v3-runtime.json'))
assert c['model_key']=='qwen3-4b' and c['max_num_seqs']==16 and not c['enforce_eager']
assert c['kv_capacity_tokens']==43664 and c.get('keepalive_connections')==0
PY
for seed in 101 102 103; do
    case "$seed" in
        101) arms=(fifo lpm_real bundle_wave packing_fifo dhas) ;;
        102) arms=(dhas packing_fifo bundle_wave lpm_real fifo) ;;
        103) arms=(lpm_real fifo dhas packing_fifo bundle_wave) ;;
    esac
    for policy in "${arms[@]}"; do
        bash scripts/v3_gateway.sh 16 "$policy"
        bash scripts/v2_reset.sh
        bash scripts/v3_run.sh "v3-opt4b-${policy}16-dev3-qps4-s${seed}" \
            "data/processed/v3/dev4b3-qps4-s${seed}.jsonl"
    done
done
