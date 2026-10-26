#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
b1_pid=${1:?usage: v2_e1_after_b1.sh B1_WATCHER_PID}
cd "$root"
log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
log "waiting for B1 watcher PID $b1_pid"
for ((i=0; i<1440; i++)); do
    if ! kill -0 "$b1_pid" 2>/dev/null; then break; fi
    sleep 30
done
if kill -0 "$b1_pid" 2>/dev/null; then
    log "B1 watcher did not finish within 12 hours"
    exit 1
fi
python3 - <<'PY_CHECK'
import json
from pathlib import Path
root = Path('results/v2')
run_id = 'v2-b1-fullctx-1qa-auto-r1'
if (root / f'{run_id}.invalid').exists():
    raise SystemExit('B1 invalid marker exists')
summary = json.loads((root / 'raw' / f'{run_id}.summary.json').read_text())
if (summary['requests'], summary['successes'], summary['errors']) != (1, 1, 0):
    raise SystemExit(f'B1 gate failed: {summary}')
PY_CHECK
for run_id in v2-e1-b2-2k-50ms-auto-r1 v2-e1-b3-2k-50ms-auto-r1; do
    if [[ -e "results/v2/raw/$run_id.jsonl" || -e "results/v2/raw/$run_id.summary.json" ]]; then
        log "E1 run artifacts already exist: $run_id"
        exit 1
    fi
done
cleanup() { bash scripts/v2_stop.sh || true; }
trap cleanup EXIT
trace=data/processed/v2/e1_2k_50ms_1pair.jsonl
log "starting B2 FIFO E1 pilot"
bash scripts/v2_start.sh B2 fifo 8
bash scripts/v2_reset.sh
bash scripts/v2_run.sh v2-e1-b2-2k-50ms-auto-r1 "$trace"
log "switching same serving engine to B3 DHAS"
bash scripts/v2_set_policy.sh dhas
bash scripts/v2_reset.sh
bash scripts/v2_run.sh v2-e1-b3-2k-50ms-auto-r1 "$trace"
python3 scripts/v2_compare_e1.py \
    --b2 v2-e1-b2-2k-50ms-auto-r1 \
    --b3 v2-e1-b3-2k-50ms-auto-r1 \
    --output results/v2/e1-2k-50ms-auto-r1.compare.json
log "matched E1 pilot complete; compare JSON saved"
