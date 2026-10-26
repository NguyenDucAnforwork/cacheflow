"""Prospectively registered continuation after an analysis-only interruption."""
import json
from pathlib import Path
from v6_full_analysis_r1 import verify_revision,REGISTRATION,FIRST
from v6_raw_archive import sha

PATH=Path('results/v3/v6full1_continuation_r1_registration.json')


def retained_outcome():
    ap=Path(f'results/v3/{FIRST}.full_audit_r1.json');zp=Path(f'results/v3/{FIRST}.archive_r1.json')
    a=json.loads(ap.read_text());assert a['complete'] is True and a['requests']==1986 and a['errors']==0
    assert a['analysis_revision_registration_sha256']==sha(REGISTRATION)
    return dict(run_id=FIRST,complete=True,audit_sha256=sha(ap),archive_sha256=sha(zp))


def verify_continuation():
    revision=verify_revision();r=json.loads(PATH.read_text())
    assert r['status']=='registered_continuation_of_unexecuted_arms_no_retries'
    assert r['reference_freeze_sha256']==sha('results/v3/v6full1_freeze.json')==revision['reference_freeze_sha256']
    assert r['analysis_registration_sha256']==sha(REGISTRATION)
    assert r['retained_outcome']==retained_outcome()
    for name,digest in r['source_sha256'].items():assert sha(name)==digest,name
    assert r['protocol_sha256']==sha(r['protocol_path'])
    freeze=json.loads(Path('results/v3/v6full1_freeze.json').read_text())
    assert freeze['actions'][0]['run_id']==FIRST and r['remaining_actions']==freeze['actions'][1:]
    assert len(r['remaining_actions'])==29 and sum(s['requests'] for s in r['remaining_actions'])==57594
    return r


def remaining_steps():
    return verify_continuation()['remaining_actions']
