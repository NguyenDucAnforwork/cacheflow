import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
import v6_analyze_fairness as module


def fixture(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);base=Path('results/v3');raw=base/'raw';raw.mkdir(parents=True)
    rid='test';rows=[dict(request_id='r',sample_id='c1',status='ok',input_tokens=10,arrival_ttft_ms=2,scheduled_arrival_ns=1_000_000,complete_ns=4_000_000)]
    (raw/(rid+'.jsonl')).write_text(json.dumps(rows[0])+'\n')
    (raw/(rid+'.summary.json')).write_text(json.dumps(dict(requests=1,successes=1,errors=0)))
    (base/(rid+'.setup.json')).write_text('{}')
    (raw/(rid+'.gateway.jsonl')).write_text(json.dumps(dict(request_id='r',input_tokens=10,status='ok',admission_wait_ms=2000,ingress_prepare_ms=10,admission_deadline_overrun_ms=1800))+'\n')
    monkeypatch.setattr(module,'admission',lambda _:dict(policy='packing_ready',max_head_bypasses=8,configured_max_bypasses=8))
    return raw,rid


def test_per_conversation_wait_keeps_deadline_overrun(tmp_path,monkeypatch):
    _,rid=fixture(tmp_path,monkeypatch);r=module.analyze(rid)
    assert r['admission']['max_head_bypasses']==8
    c=r['by_conversation'][0];assert c['requests']==1 and c['admission_wait_ms']['max']==2000
    assert c['admission_deadline_overrun_requests']==1 and c['completion_latency_ms']['p95']==3


def test_failed_run_and_bypass_violation_cannot_be_hidden(tmp_path,monkeypatch):
    raw,rid=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(module,'admission',lambda _:dict(policy='packing_ready',max_head_bypasses=9,configured_max_bypasses=8))
    with pytest.raises(AssertionError):module.analyze(rid)
    (raw/(rid+'.summary.json')).write_text(json.dumps(dict(requests=2,successes=1,errors=1)))
    with pytest.raises(AssertionError):module.analyze(rid)
