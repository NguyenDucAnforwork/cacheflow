#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
trace=data/processed/v2/e1_2k_50ms_1pair.jsonl
for run_id in v2-e1-b2-2k-50ms-r2 v2-e1-b3-2k-50ms-r2 v2-e1-b3-2k-50ms-r3 v2-e1-b2-2k-50ms-r3; do
    if [[ -e "results/v2/raw/$run_id.jsonl" || -e "results/v2/raw/$run_id.summary.json" ]]; then
        log "refusing duplicate run ID $run_id"
        exit 1
    fi
done
cleanup() { bash scripts/v2_stop.sh || true; }
trap cleanup EXIT
log "starting two additional controlled 2K/50ms E1 replicates"
bash scripts/v2_start.sh B2 fifo 8
bash scripts/v2_reset.sh
bash scripts/v2_run.sh v2-e1-b2-2k-50ms-r2 "$trace"
bash scripts/v2_set_policy.sh dhas
bash scripts/v2_reset.sh
bash scripts/v2_run.sh v2-e1-b3-2k-50ms-r2 "$trace"
python3 scripts/v2_compare_e1.py --b2 v2-e1-b2-2k-50ms-r2 --b3 v2-e1-b3-2k-50ms-r2 --output results/v2/e1-2k-50ms-r2.compare.json
bash scripts/v2_reset.sh
bash scripts/v2_run.sh v2-e1-b3-2k-50ms-r3 "$trace"
bash scripts/v2_set_policy.sh fifo
bash scripts/v2_reset.sh
bash scripts/v2_run.sh v2-e1-b2-2k-50ms-r3 "$trace"
python3 scripts/v2_compare_e1.py --b2 v2-e1-b2-2k-50ms-r3 --b3 v2-e1-b3-2k-50ms-r3 --output results/v2/e1-2k-50ms-r3.compare.json
log "E1 replicate pairs r2 and r3 complete"
