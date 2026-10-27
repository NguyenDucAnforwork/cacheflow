"""The conditional result must retain its assumptions and positive control."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from v8_allocation_witness import run


def test_installed_allocation_bodies_reject_duplicate_case_but_accept_shared_control():
    r=run();assert r['logical_union_reservation_pages']==158<r['usable_capacity_pages']==160
    assert r['cases'][0]['initial_free_blocks']==32 and r['cases'][1]['initial_free_blocks']==96
    assert all(q['additional_blocks_needed']==40 for c in r['cases'] for q in c['outcomes'])
    assert all(q['allocation_rejected'] for q in r['cases'][0]['outcomes'])
    assert not any(q['allocation_rejected'] for q in r['cases'][1]['outcomes'])
    assert not r['gpu_execution'] and not r['live_state_reproduced'] and len(r['native_method_bodies'])==3
