"""Projected process ledgers only; not evidence of full GPU execution."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_audit_full import fresh_process_units
from v6_full_plan import build_plan


def ledger():
    return [dict(step,engine_pid=1000+i,lmcache_pid=2000+i if step['engine']=='main' else None)
            for i,step in enumerate(build_plan())]


def test_distinct_engines_do_not_hide_a_retained_cpu_tier():
    rows=ledger();assert fresh_process_units(rows)['distinct_main_lmcache_pids']==12
    assert len({r['engine_pid'] for r in rows})==30
    for row in rows:
        if row['engine']=='main':row['lmcache_pid']=999
    with pytest.raises(AssertionError,match='Process retained'):fresh_process_units(rows)


@pytest.mark.parametrize('pid',[None,0,-1,True,'123'])
def test_missing_or_invalid_cpu_identity_rejects_the_complete_stage(pid):
    rows=ledger();next(r for r in rows if r['engine']=='main')['lmcache_pid']=pid
    with pytest.raises(AssertionError,match='Missing/invalid'):fresh_process_units(rows)


def test_incomplete_or_reused_engine_units_are_rejected():
    rows=ledger()
    with pytest.raises(AssertionError):fresh_process_units(rows[:-1])
    rows[-1]['engine_pid']=rows[0]['engine_pid']
    with pytest.raises(AssertionError,match='Process retained'):fresh_process_units(rows)
