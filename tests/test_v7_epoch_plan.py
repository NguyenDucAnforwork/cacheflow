"""Preserve strong references, three-seed order and explicit implementation IDs."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v7_epoch_plan import build_plan


def test_fixed_screen_retains_same_policy_and_strong_baselines_without_old_process_pairs():
    rows=build_plan();assert len(rows)==18 and len({r['run_id'] for r in rows})==18
    assert sum(r['requests'] for r in rows)==sum(r['warmup_requests'] for r in rows)==1080
    for engine,strong in [('main','bundle16'),('sg','native_dfs')]:
        for seed in [101,102,103]:
            block=[r for r in rows if r['engine']==engine and r['seed']==seed]
            assert {r['arm'] for r in block}=={strong,'union64','epoch_union64'}
            old=next(r for r in block if r['arm']=='union64');new=next(r for r in block if r['arm']=='epoch_union64')
            assert old['policy']==new['policy']=='packing_reuse' and old['implementation']=='reference' and new['implementation']=='epoch'
            for key in ['trace','cap','host_payload_bytes','gpu_kv_gib','max_queue','max_bypasses','timeout_s','native_policy']:assert old[key]==new[key]
    first=[(r['engine'],r['arm']) for r in rows[:6]]
    assert [(r['engine'],r['arm']) for r in rows[6:12]]==first[::-1]
    assert [(r['engine'],r['arm']) for r in rows[12:]]==first[3:]+first[:3]
