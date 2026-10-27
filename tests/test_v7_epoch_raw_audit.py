"""CPU projected-V7 metadata over copies of real60QA data; not V7 inference.

Identity/configuration fields below are deliberately synthetic test fixtures.
Original files and results are untouched; no derived timing is reported as V7.
"""
import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
import v7_audit_epoch_run as module
from v7_gateway_identity import ROOT,SOURCES
from v6_raw_archive import sha
from test_v7_epoch_contracts import projected


def fixture(tmp_path,monkeypatch,engine):
    step,setup,_,entry,parent,seal,freeze=projected(engine);rid=step['run_id']
    old='v6dev1-main-union64-s101' if engine=='main' else 'v6native1-primary-s101-union64'
    meta=ROOT/('results/v3' if engine=='main' else 'results/v3/sglang');raw=ROOT/('results/v3/raw' if engine=='main' else 'results/v3/raw/sglang')
    targetmeta=tmp_path/('results/v3' if engine=='main' else 'results/v3/sglang');targetraw=tmp_path/('results/v3/raw' if engine=='main' else 'results/v3/raw/sglang')
    targetmeta.mkdir(parents=True);targetraw.mkdir(parents=True)
    summary=json.loads((raw/(old+'.summary.json')).read_text());summary.update(run_id=rid,request_read_timeout_s=180,request_pool_timeout_s=180)
    setup['run_id']=rid;write=lambda p,d:Path(p).write_text(json.dumps(d)+'\n')
    for suffix in ['.jsonl','.outputs.jsonl','.gateway.jsonl']:
        values=[json.loads(l) for l in (raw/(old+suffix)).read_text().splitlines()]
        for r in values:r['run_id']=rid
        (targetraw/(rid+suffix)).write_text(''.join(json.dumps(r)+'\n' for r in values))
    requests=[json.loads(l) for l in (targetraw/(rid+'.jsonl')).read_text().splitlines()]
    shutil.copyfile(raw/(old+'.metrics.jsonl'),targetraw/(rid+'.metrics.jsonl'))
    write(targetraw/(rid+'.summary.json'),summary)
    for suffix in ['.metrics_summary.json','.itl_histogram.json']:
        d=json.loads((meta/(old+suffix)).read_text());d['run_id']=rid
        if suffix=='.itl_histogram.json':d['request_file_sha256']=sha(targetraw/(rid+'.jsonl'))
        write(targetmeta/(rid+suffix),d)
    low=min(r['scheduled_arrival_ns'] for r in requests);high=max(r['complete_ns'] for r in requests)
    identity=dict(implementation='reference',policy='packing_reuse',scheduler_class='cacheflow.v3_memory_scheduler.ResidencyScheduler',
        selector='cacheflow.v3_memory_scheduler.ResidencyScheduler._choose',source_sha256={str((ROOT/n).resolve()):sha(ROOT/n) for n in SOURCES})
    before=dict(gateway_pid=123,gateway_create_time=1.,gateway_argv=['uvicorn','cacheflow.v7_gateway:create_app'],implementation_record=identity,
        observer_source_sha256=sha(ROOT/'scripts/v7_gateway_identity.py'),start_ns=low-2000,end_ns=low-1000,health=setup['gateway_before'])
    after=copy.deepcopy(before);after.update(start_ns=high+1000,end_ns=high+2000,health=setup['gateway_after'])
    step['implementation']='reference'
    if engine=='main':
        entry['gateway_pid']=123;write(targetmeta/(rid+'.v7_entrypoint.json'),entry)
        for label,d in [('before',before),('after',after)]:write(targetmeta/(rid+'.v7_identity_'+label+'.json'),d)
        write(targetmeta/(rid+'.v7_identity_pair.json'),dict(complete_identity_pair=True,request_file_sha256=sha(targetraw/(rid+'.jsonl')),
            before_sha256=sha(targetmeta/(rid+'.v7_identity_before.json')),after_sha256=sha(targetmeta/(rid+'.v7_identity_after.json'))))
    else:
        setup['gateway_runtime_entrypoint']['pid']=123;setup['gateway_implementation_before']=before;setup['gateway_implementation_after']=after
    write(targetmeta/(rid+'.setup.json'),setup)
    trace='data/processed/v3/v5-dev4b3-qps4-s101.jsonl';step['trace']=trace
    (tmp_path/trace).parent.mkdir(parents=True)
    for p in [Path(trace),Path(trace).with_suffix('.manifest.json')]:shutil.copyfile(ROOT/p,tmp_path/p)
    monkeypatch.chdir(tmp_path)
    return step,freeze,parent,seal,targetraw,targetmeta


@pytest.mark.parametrize('engine',['main','sg'])
def test_real_raw_layout_with_projected_v7_identity_is_accepted(tmp_path,monkeypatch,engine):
    step,freeze,parent,seal,raw,meta=fixture(tmp_path,monkeypatch,engine)
    result=module.check_phase(step,freeze,parent,seal)
    assert len(result[2])==60 and len(result[4])==5 and len(result[5])==(7 if engine=='main' else 3)


@pytest.mark.parametrize('engine',['main','sg'])
def test_raw_output_tampering_cannot_pass_through_new_configuration_audit(tmp_path,monkeypatch,engine):
    step,freeze,parent,seal,raw,meta=fixture(tmp_path,monkeypatch,engine)
    path=raw/(step['run_id']+'.outputs.jsonl');rows=[json.loads(l) for l in path.read_text().splitlines()];rows[0]['output']='changed'
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    with pytest.raises(AssertionError):module.check_phase(step,freeze,parent,seal)
