#!/usr/bin/env bash
# Cold-start B1/B2 tiering replicates. Generated prompts remain ignored.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
run_arm() {
    local mode=$1 gib=$2 seed=$3
    local id="v2-e2-${mode,,}-${gib}g-dev3-qps02-s${seed}"
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
    CACHEFLOW_CAPTURE_TEXT=1 bash scripts/v2_run.sh "$id" "data/processed/v2/e2_dev3_qps02_s${seed}.jsonl"
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
# Reverse arm and budget order in seed 29. Each run restarts the serving stack.
for seed in 17 29 43; do
    if [[ "$seed" == 29 ]]; then
        for gib in 8 4; do
            run_arm B2 "$gib" "$seed"
            run_arm B1 "$gib" "$seed"
        done
    else
        for gib in 4 8; do
            run_arm B1 "$gib" "$seed"
            run_arm B2 "$gib" "$seed"
        done
    fi
done
