import json
import subprocess
from pathlib import Path


def test_confirmation_plan_covers_frozen_arms_seeds_and_preserves_runtime_state():
    markers=[Path('.cacheflow-v3-runtime.json'),Path('.cacheflow-sglang-runtime.json')]
    before={str(p):p.read_bytes() for p in markers if p.exists()}
    steps=list(map(json.loads,subprocess.check_output(['/venv/main/bin/python','scripts/v4_confirm.py','--plan'],text=True).splitlines()))
    measured=[s for s in steps if s['kind'] in {'sg','main'} and '-warm-' not in s['run_id']]
    assert len(measured)==len({s['run_id'] for s in measured})==27
    assert sum(s['kind']=='sg' for s in measured)==18
    assert sum(s['kind']=='main' for s in measured)==9
    assert {s['run_id'].rsplit('-s',1)[1] for s in measured}=={'701','702','703'}
    assert [s['policy'] for s in steps if s['kind']=='start_sg']==['lpm','dfs-weight']
    for s in measured:
        assert Path(s['trace']).is_file()
        m=json.loads(Path(s['trace']).with_suffix('.manifest.json').read_text())
        assert m['requests']==40 and m['selected_samples']==['conv-43','conv-44']
    assert {str(p):p.read_bytes() for p in markers if p.exists()}==before
