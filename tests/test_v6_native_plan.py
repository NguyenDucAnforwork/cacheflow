import sys
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_native_matrix import build_plan,ARMS,SOURCES


def test_native_plan_scope_and_balanced_orders():
    blocks=build_plan();assert len(blocks)==18
    measured=[s for b in blocks for s in b['actions']]
    assert len(measured)==60 and sum(s['requests'] for s in measured)==2700
    assert sum(b['warmup']['requests'] for b in blocks)==1080
    assert len({s['run_id'] for s in measured})==60
    assert all(Path(name).is_file() for name in SOURCES)
    for regime in {b['regime'] for b in blocks}:
        bb=[b for b in blocks if b['regime']==regime];assert [b['seed'] for b in bb]==[101,102,103]
        first=[s['arm'] for s in bb[0]['actions']];second=[s['arm'] for s in bb[1]['actions']]
        assert first==list(reversed(second))
        assert set(first)==(set(ARMS) if regime=='primary' else {'native','union64','packing_ready'})
    assert {b['native_policy'] for b in blocks}=={'lpm','dfs-weight'}
    assert [b['budget'] for b in blocks if b['regime']=='gpufit']==[10,10,10]
