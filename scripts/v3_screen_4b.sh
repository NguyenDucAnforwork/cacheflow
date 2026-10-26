#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
for ((attempt=0; attempt<240; attempt++)); do
    if curl --silent --fail --max-time 2 http://127.0.0.1:8100/health >/dev/null; then break; fi
    sleep 2
done
curl --silent --fail --max-time 2 http://127.0.0.1:8100/health >/dev/null
/venv/main/bin/python - <<'PY'
import json,urllib.request
body=dict(model='cacheflow-qwen3-4b',prompt='Return one word: ready.',max_tokens=4,temperature=0,add_special_tokens=False)
r=urllib.request.Request('http://127.0.0.1:8000/v1/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
x=json.load(urllib.request.urlopen(r,timeout=120));assert x['usage']['completion_tokens']>0
print('Fixed tiny 4B warmup complete')
PY
for qps in 2 4; do
    for arm in fifo:16 fifo:4 packing_fifo:4 packing_fifo:16 lpm_real:16 residency:16 bundle_wave:16; do
        policy=${arm%:*};cap=${arm#*:}
        bash scripts/v3_gateway.sh "$cap" "$policy"
        bash scripts/v2_reset.sh
        bash scripts/v3_run.sh "v3-4b-${policy}${cap}-dev3-qps${qps}-s101" \
            "data/processed/v3/dev4b3-qps${qps}-s101.jsonl"
    done
done
