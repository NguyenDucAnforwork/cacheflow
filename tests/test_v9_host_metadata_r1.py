from pathlib import Path
import json
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import v8_diagnostic_capture as base
import v9_repair_r1 as driver
from v9_repair_capture_r1 import capture_source


def test_actual_controller_host_filename_passes_real_collector_freshness(monkeypatch,tmp_path):
    output=tmp_path/'results';output.mkdir();raw=output/'raw';raw.mkdir();rid='v9repair2-probe-reference-s101'
    (output/(rid+'-host-status.json')).write_text('{}')
    (raw/(rid+'-engine.log')).write_text('startup log')
    source,_=capture_source();scope=dict(vars(base),BASE=output,RAW=raw)
    class ReachedHealth(Exception):pass
    def health():raise ReachedHealth('Freshness passed; no GPU/HTTP call')
    scope['health']=health;exec(compile(source,'real_capture_preflight','exec'),scope)
    with pytest.raises(ReachedHealth):scope['capture'](dict(run_id=rid),'registration')
    (output/(rid+'.diagnostic_setup.json')).write_text('{}')
    with pytest.raises(AssertionError):scope['capture'](dict(run_id=rid),'registration')


def test_only_namespace_changes_action_graph_and_host_name_is_corrected():
    from v9_repair import plan as old_plan
    assert driver.plan()==[dict(s,run_id=s['run_id'].replace('v9repair1','v9repair2'),proof_label=s['proof_label'].replace('v9repair1','v9repair2'),probe_label=s['probe_label'].replace('v9repair1','v9repair2')) for s in old_plan()]
    source=Path('scripts/v9_repair_r1.py').read_text();audit=Path('scripts/v9_audit_repair_r1.py').read_text()
    assert "step['run_id']+'-host-status.json'" in source and "rid+'-host-status.json'" in audit
    assert "step['run_id']+'-engine.log'" in source and "rid+'-engine.log'" in audit
    assert "step['run_id']+'.host_status.json'" not in source
    assert "step['run_id']+'.engine.log'" not in source
