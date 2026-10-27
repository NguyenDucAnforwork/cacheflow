import copy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import v8_diag3 as driver


def test_rebound_verifier_uses_new_protocol_globals(monkeypatch,tmp_path):
    protocol=tmp_path/'new_protocol.md';protocol.write_text('new namespace')
    monkeypatch.setattr(driver,'PROTOCOL',protocol)
    scope=driver.controller_scope()
    assert scope['verify_pins'].__globals__ is scope and scope['probe_coverage'].__globals__ is scope
    r=json.loads(Path('results/v3/v8diag1_registration.json').read_text())
    r['protocol_sha256']=hashlib.sha256(protocol.read_bytes()).hexdigest()
    # Other checks use the real immutable small metadata; source maps are empty
    # here to isolate global binding, not to claim source proof.
    r['source_sha256']={};r['native_source_sha256']={}
    scope['verify_pins'](r)


def test_rebound_coverage_reads_new_journal_prefix(monkeypatch,tmp_path):
    scope=driver.controller_scope();scope['BASE']=tmp_path
    raw=tmp_path/'raw';raw.mkdir();rows=[]
    for target in ['scheduler','allocator','connector','worker']:
        rows.append(dict(kind='hook_ready',target=target,source_path='native.py',source_sha256='digest'))
    rows.extend(dict(kind=k) for k in ['scheduler','connector_metadata','connector_worker'])
    for i,row in enumerate(rows):row.update(diagnostic_only=True,monotonic_ns=i)
    (raw/'v8diag3-probe.7.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    result=scope['probe_coverage'](dict(native_source_sha256={'native.py':'digest'}))
    assert result['native_metadata_coverage_checked']
    assert list(result['journal_sha256'])==[str(raw/'v8diag3-probe.7.jsonl')]
