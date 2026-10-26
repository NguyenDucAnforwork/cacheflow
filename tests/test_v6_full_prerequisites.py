"""Use actual terminal main/native schemas; projected controls are not results."""
import copy
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_freeze_full import validate_prerequisite,PREREQUISITES
from v6_main_controls import build_plan


def test_actual_completed_audits_are_accepted_without_rewriting_old_schema():
    for name,n,q in PREREQUISITES[:2]:
        data=Path(name).read_bytes();audit=json.loads(data)
        validate_prerequisite(name,audit,n,q)
        assert Path(name).read_bytes()==data
    assert 'complete' not in json.loads(Path(PREREQUISITES[0][0]).read_text())


def test_legacy_main_still_requires_complete_counts_unique_runs_and_terminal_scope():
    name,n,q=PREREQUISITES[0];original=json.loads(Path(name).read_text())
    for mutate in [lambda a:a['runs'].pop(),lambda a:a['runs'].__setitem__(0,a['runs'][1]),
                   lambda a:a.update(errors=1),lambda a:a.update(requests=1439),
                   lambda a:a.update(scope='Incomplete checkpoint'),lambda a:a.update(complete=False),
                   lambda a:a['runs'][0].update(requests=59)]:
        audit=copy.deepcopy(original);mutate(audit)
        with pytest.raises(AssertionError):validate_prerequisite(name,audit,n,q)


def test_modern_controls_require_explicit_complete_flag_even_with_all_counts():
    name,n,q=PREREQUISITES[2]
    audit=dict(complete=True,errors=0,requests=1260,runs=build_plan())
    validate_prerequisite(name,audit,n,q)
    audit.pop('complete')
    with pytest.raises(KeyError):validate_prerequisite(name,audit,n,q)
    audit['complete']=False
    with pytest.raises(AssertionError):validate_prerequisite(name,audit,n,q)
