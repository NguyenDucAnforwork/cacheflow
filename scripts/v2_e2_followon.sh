#!/usr/bin/env bash
# Continue only after the verified dev matrix process terminates successfully.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
pid=${1:?usage: v2_e2_followon.sh MATRIX_PID}
[[ -r /proc/$pid/stat ]] || { echo 'matrix PID not live'; exit 1; }
start=$(awk '{print $22}' "/proc/$pid/stat")
while [[ -r /proc/$pid/stat ]] && [[ $(awk '{print $22}' "/proc/$pid/stat") == "$start" ]]; do
    sleep 2
done
/venv/main/bin/python scripts/v2_analyze_e2.py
/venv/main/bin/python - <<'PY'
import json
from pathlib import Path
base=Path('results/v2')
a=json.loads((base/'e2_aggregate.json').read_text())
assert a['4']['p95_relative_change_pct']['n_runs']==3
assert a['4']['p95_relative_change_pct']['mean'] < -10, 'no meaningful dev p95 gain'
for seed in (17,29,43):
    c=json.loads((base/f'e2-4g-s{seed}.compare.json').read_text())
    work=c['counters']['computed_prefill_tokens']
    assert work['b2'] < work['b1'], 'no dev recomputation gain'
    assert c['counters']['actual_external_tokens']['b2'] > 0, 'no actual CPU restore'
print('DEV MECHANISM GATE PASSED; starting frozen holdout confirmation')
PY
# Leave time for the owner-facing report inside the 90-minute session budget.
[[ $(date -u +%s) -lt $(date -u -d '2026-10-26 04:55:00' +%s) ]] || { echo 'insufficient budget for confirmation'; exit 1; }
bash scripts/v2_e2_confirmation.sh
/venv/main/bin/python scripts/v2_analyze_e2.py --cohort holdout2 --budgets 4 --seeds 101 211 307
bash scripts/v2_e2_supplement.sh chat
bash scripts/v2_e2_supplement.sh session
/venv/main/bin/python scripts/v2_plot_e2.py
PYTHONPATH=src /venv/main/bin/python - <<'PY'
import json,subprocess
from pathlib import Path
ids=[]
for p in sorted(Path('results/v2/raw').glob('v2-e[23]-*.summary.json')):
    s=json.loads(p.read_text())
    if 'gate' not in s['run_id']:
        ids.append(s['run_id'])
subprocess.run(['/venv/main/bin/python','scripts/v2_quality_audit.py','--run-ids',*ids,
                '--output','results/v2/e2_quality.json'],check=True)
PY
/venv/main/bin/python scripts/v2_summarize_quality.py --input results/v2/e2_quality.json --output results/v2/e2_quality_pairs.json
printf '%s ALL FOLLOW-ON WORK COMPLETE\n' "$(date -u +%FT%TZ)"
