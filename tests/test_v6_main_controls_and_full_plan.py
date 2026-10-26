import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_main_controls import build_plan as controls
from v6_full_plan import build_plan as full


def test_controls_match_regimes_and_existing_manifests():
    steps=controls();assert len(steps)==36 and sum(s['requests'] for s in steps)==1260
    assert len({s['run_id'] for s in steps})==36
    for s in steps:
        assert json.loads(Path(s['trace']).with_suffix('.manifest.json').read_text())['requests']==s['requests']
    for regime in ['lowload','lowreuse','gpufit','abstention']:
        rr=[s for s in steps if s['regime']==regime];assert len(rr)==9
        assert {s['seed'] for s in rr}=={101,102,103}
        assert {s['arm'] for s in rr}=={'fifo64','union64','packing_ready'}
        assert {s['budget'] for s in rr}==({10} if regime=='gpufit' else {6})


def test_full_scope_preserves_original_union_readiness_and_strong_native_controls():
    steps=full();assert len(steps)==30 and sum(s['requests'] for s in steps)==59580
    assert len({s['run_id'] for s in steps})==30
    for seed in [901,902,903]:
        main=[s for s in steps if s['seed']==seed and s['engine']=='main']
        sg=[s for s in steps if s['seed']==seed and s['engine']=='sg' and s['budget']==6]
        assert {s['arm'] for s in main}=={'fifo64','bundle16','union64','packing_ready'}
        assert {s['arm'] for s in sg}=={'native_lpm','native_dfs','fifo64','union64','packing_ready'}
    larger=[s for s in steps if s['budget']==10]
    assert {s['arm'] for s in larger}=={'native_lpm','union64','packing_ready'}
    assert all(s['host_flag']==48 and s['queue']==512 for s in steps)
    for s in steps:
        assert json.loads(Path(s['trace']).with_suffix('.manifest.json').read_text())['requests']==1986
