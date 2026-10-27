import ast
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import v8_diag2 as driver
import v8_diag2_capture as capture


def test_capture_change_is_reversible_and_only_post_replay_accounting():
    source,proof=capture.capture_source();text=Path('scripts/v8_diagnostic_capture.py').read_text()
    for change in reversed(proof['changes']):
        assert source.count(change['new'])==1;source=source.replace(change['new'],change['old'],1)
    fn=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='capture')
    assert source==ast.get_source_segment(text,fn)


def test_controller_changes_keep_failure_cleanup_and_only_unexecuted_phases():
    source,proof=driver.controller_source();text=Path('scripts/v8_full_liveness_diagnostic.py').read_text()
    assert "for phase in ['on','offB']:" in source and 'len(outcomes)==4' in source
    assert 'finally:' in source and "stage='restore_config'" in source
    for change in reversed(proof['changes']):
        assert source.count(change['new'])==1;source=source.replace(change['new'],change['old'],1)
    fn=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='execute')
    assert source==ast.get_source_segment(text,fn)


def test_absent_engine_requires_errors_and_cannot_pass_as_verified_identity(monkeypatch):
    old=dict(pid=10,birth=123,argv=['engine']);before=[('cacheflow_v2_vllm',old)]
    monkeypatch.setattr(capture.original,'service_pid',lambda n:0)
    with pytest.raises(AssertionError):capture.bookends(before,dict(errors=0))
    result=capture.bookends(before,dict(errors=1))
    assert result['cacheflow_v2_vllm']['end_identity_verified'] is False
    with pytest.raises(AssertionError):capture.bookends([('cacheflow_v2_lmcache',old)],dict(errors=1))


def test_replaced_engine_rejected_even_after_request_errors(monkeypatch):
    monkeypatch.setattr(capture.original,'service_pid',lambda n:11)
    monkeypatch.setattr(capture.original,'process',lambda n:dict(pid=11,birth=456,argv=['engine']))
    with pytest.raises(AssertionError,match='replaced'):capture.bookends([('cacheflow_v2_vllm',dict(pid=10,birth=123,argv=['engine']))],dict(errors=1))
