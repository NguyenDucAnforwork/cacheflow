"""No change to the actual real-prefix/state comparison kernel."""
import ast
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import v8_epoch_trace_revision as revision


def test_explicit_transform_keeps_all_native_prefix_and_state_checks():
    source,proof=revision.revised_source();original=revision.ORIGINAL.read_text()
    tree=ast.parse(original);fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='execute')
    restored=source
    assert len(proof['replacements'])==4
    for change in reversed(proof['replacements']):
        assert restored.count(change['new'])==1
        restored=restored.replace(change['new'],change['old'],1)
    assert restored==ast.get_source_segment(original,fn)
    assert 'len(templates)==1986 and total_tokens==50522325' in source
    assert 'compare_ledger_states(records,templates,settings,stride=' in source
    assert 'production_decision_trace_reproduced=False' in source
    assert 'terminal_full_audit_sha256' not in source


def test_changed_original_prerequisite_cannot_silently_transform(monkeypatch,tmp_path):
    path=tmp_path/'changed.py';path.write_text(revision.ORIGINAL.read_text().replace("full['requests']==59580","full['requests']==1986"))
    monkeypatch.setattr(revision,'ORIGINAL',path)
    with pytest.raises(AssertionError):revision.revised_source()


def test_incomplete_checkpoint_is_not_accepted_as_successful_full(monkeypatch,tmp_path):
    checkpoint=tmp_path/'checkpoint.json';failed=tmp_path/'failed.json'
    checkpoint.write_text(json.dumps(dict(complete=True,kind='interim_full_checkpoint_not_terminal_audit')));failed.write_text('{}')
    monkeypatch.setattr(revision,'CHECKPOINT',checkpoint);monkeypatch.setattr(revision,'FAILED',failed)
    with pytest.raises(AssertionError):revision.validate_failed_full_checkpoint(dict(evidence_sha256={}))
