import json
import subprocess
from pathlib import Path


def test_full_plan_has_three_primary_repetitions_and_explicit_single_seed_controls():
    markers=[Path('.cacheflow-v3-runtime.json'),Path('.cacheflow-sglang-runtime.json')]
    before={str(p):p.read_bytes() for p in markers if p.exists()}
    steps=list(map(json.loads,subprocess.check_output(['/venv/main/bin/python','scripts/v4_full.py','--plan'],text=True).splitlines()))
    measured=[s for s in steps if s['kind'] in {'sg','main'} and '-warm-' not in s['run_id']]
    assert len(measured)==len({s['run_id'] for s in measured})==17
    primary=[s for s in measured if '-sg-g6-' in s['run_id']]
    assert len(primary)==12
    for seed in [901,902,903]:
        rows=[s for s in primary if s['run_id'].endswith(f'-s{seed}')]
        assert {s['run_id'].split('-qps4-')[1].split('-s')[0] for s in rows}=={'native','fifo','union','dfs'}
    assert len([s for s in measured if '-sg-g10-' in s['run_id']])==2
    assert len([s for s in measured if s['kind']=='main'])==3
    assert {str(p):p.read_bytes() for p in markers if p.exists()}==before
