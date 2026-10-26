#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
trace=data/processed/v2/e1_2k_50ms_4pairs.jsonl
for run_id in v2-e1-b2-2k-50ms-4pairs-r1 v2-e1-b3-2k-50ms-4pairs-r1; do
    if [[ -e "results/v2/raw/$run_id.jsonl" || -e "results/v2/raw/$run_id.summary.json" ]]; then
        echo "duplicate run ID: $run_id" >&2
        exit 1
    fi
done
cleanup() { bash scripts/v2_stop.sh || true; }
trap cleanup EXIT
bash scripts/v2_start.sh B2 fifo 8
bash scripts/v2_reset.sh
bash scripts/v2_run.sh v2-e1-b2-2k-50ms-4pairs-r1 "$trace"
bash scripts/v2_set_policy.sh dhas
bash scripts/v2_reset.sh
bash scripts/v2_run.sh v2-e1-b3-2k-50ms-4pairs-r1 "$trace"
python3 scripts/v2_compare_e1.py --b2 v2-e1-b2-2k-50ms-4pairs-r1 --b3 v2-e1-b3-2k-50ms-4pairs-r1 --output results/v2/e1-2k-50ms-4pairs-r1.compare.json
