from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v8_replay_observed_store_metadata import candidates,replay_scalar_store


def test_observed_lower_bound_requires_preceding_same_process_and_native_store_differs():
    tracker=dict(state='READY',num_stored_tokens=81920,num_scheduled_tokens=640,vllm_hit_tokens=0,lmcache_hit_tokens=1024,allocated_blocks_per_group={'0':104})
    rows=[dict(kind='scheduler',pid=7,monotonic_ns=1,requests=[dict(request_id='a',num_tokens=1664)]),
        dict(kind='connector_metadata',pid=7,monotonic_ns=2,tracker_states={'a':tracker})]
    cases=candidates(rows);assert len(cases)==1 and cases[0]['conditional_eligible_store_tokens']==512
    assert replay_scalar_store(cases[0],81920)[0] is None
    assert replay_scalar_store(cases[0],1024)[0]==dict(direction='STORE',start=1024,end=1536)
    rows[1]['pid']=8;assert candidates(rows)==[]
