import json,subprocess
from pathlib import Path


def test_repair_plans_keep_repetitions_baselines_and_do_not_touch_runtime():
    markers=[Path('.cacheflow-v3-runtime.json'),Path('.cacheflow-sglang-runtime.json')]
    before={str(p):p.read_bytes() for p in markers if p.exists()}
    for script,expected in [('v5_validate.py',57),('v5_confirm.py',27),('v5_full.py',17)]:
        rows=list(map(json.loads,subprocess.check_output(['/venv/main/bin/python','scripts/'+script,'--plan'],text=True).splitlines()))
        measured=[r for r in rows if r['kind'] in {'sg','main'} and '-warm-' not in r['run_id']]
        assert len(measured)==len({r['run_id'] for r in measured})==expected
        assert all('/v5-' in r['trace'] for r in measured)
    assert {str(p):p.read_bytes() for p in markers if p.exists()}==before
