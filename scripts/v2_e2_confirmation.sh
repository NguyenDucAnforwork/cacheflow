#!/usr/bin/env bash
# Held-out conversation confirmation of pressure-regime tiering.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
run_arm() {
    local mode=$1 gib=$2 seed=$3
    local id="v2-e2-${mode,,}-${gib}g-holdout2-qps02-s${seed}"
    echo "$(date -u +%FT%TZ) START $id"
    bash scripts/v2_start.sh "$mode" fifo "$gib"
    # Identical tiny engine warmup; reset both cache tiers afterwards.
    curl --silent --show-error --fail --max-time 60 http://127.0.0.1:8000/v1/completions \
        -H 'Content-Type: application/json' \
        -d '{"model":"cacheflow-qwen3-1.7b","prompt":"A brief warmup. Answer: 1","max_tokens":1,"temperature":0}' >/dev/null
    bash scripts/v2_reset.sh
    curl --silent --fail http://127.0.0.1:8100/health > "results/v2/raw/$id.reset_health.json"
    if [[ "$mode" == B2 ]]; then
        curl --silent --fail http://127.0.0.1:18080/metrics > "results/v2/raw/$id.reset_lmcache.prom"
    fi
    CACHEFLOW_CAPTURE_TEXT=1 bash scripts/v2_run.sh "$id" "data/processed/v2/e2_holdout2_qps02_s${seed}.jsonl"
    /venv/main/bin/python - "$id" <<'PY'
import json, sys
from pathlib import Path
run_id = sys.argv[1]
p = Path('results/v2/raw')
s = json.loads((p / f'{run_id}.summary.json').read_text())
rows = [json.loads(x) for x in (p / f'{run_id}.jsonl').read_text().splitlines()]
assert s['errors'] == 0 and s['successes'] == 30, s
assert all(r['input_tokens'] == r['server_prompt_tokens'] for r in rows)
assert (p / f'{run_id}.outputs.jsonl').exists()
print('VALIDATED', run_id, s['arrival_ttft_p50_ms'], s['arrival_ttft_p95_ms'])
PY
    echo "$(date -u +%FT%TZ) DONE $id"
}
trap 'bash scripts/v2_stop.sh' EXIT
# Frozen new seeds and alternating arm order.
for seed in 101 211 307; do
    if [[ "$seed" == 211 ]]; then
        run_arm B2 4 "$seed"
        run_arm B1 4 "$seed"
    else
        run_arm B1 4 "$seed"
        run_arm B2 4 "$seed"
    fi
done
