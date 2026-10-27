"""Queued real-prefix/ledger-state validation, not exact decision replay or speed."""
import argparse
import asyncio
import gzip
import hashlib
import importlib.metadata
import json
import struct
from datetime import datetime,timezone
from pathlib import Path
import psutil
import yaml
from cacheflow.scheduler import Ticket
from cacheflow.prefix import group_digest
from cacheflow.v4_prepare import prepare
from cacheflow.v7_trace_states import compare_ledger_states
from v3_model import get_model
from v6_raw_archive import sha,expanded
from v6_trace_hashes import CanonicalTraceDigest
from v6_regenerate_full_inputs import wait_parent,idle,FREEZE

BASE=Path('results/v3');PARENT=BASE/'v7_epoch_cpu_probe_registration.json';FULL=BASE/'v6full1_audit_r1.json'


def register(pid,path):
    path=Path(path);assert not path.exists();p=psutil.Process(pid);argv=p.cmdline()
    assert p.is_running() and p.status()!=psutil.STATUS_ZOMBIE
    assert argv[-3:]==['scripts/v7_epoch_cpu_probe.py','execute',str(PARENT)]
    freeze=json.loads(FREEZE.read_text());targets=[s['run_id'] for s in freeze['actions'] if s['engine']=='main' and s['seed']==901 and s['arm'] in {'union64','packing_ready'}]
    assert len(targets)==2
    sources=[__file__,'src/cacheflow/v7_trace_states.py','src/cacheflow/v7_epoch_scheduler.py','src/cacheflow/v6_ready_scheduler.py',
        'src/cacheflow/v3_memory_scheduler.py','src/cacheflow/scheduler.py','src/cacheflow/prefix.py','src/cacheflow/v3_residency.py',
        'src/cacheflow/v4_prepare.py','scripts/v3_model.py','scripts/v6_raw_archive.py','scripts/v6_trace_hashes.py','scripts/v6_regenerate_full_inputs.py']
    r=dict(kind='real_prefix_ledger_state_validation_not_production_trace_replay',registered_utc=datetime.now(timezone.utc).isoformat(),
        after_pid=pid,after_create_time=p.create_time(),after_argv=argv,parent_registration_sha256=sha(PARENT),freeze_sha256=sha(FREEZE),
        target_run_ids=targets,event_stride=16,stable_polls=3,source_sha256={str(p):sha(p) for p in sources},
        scope='After exactCPUprobe parent succeeds and services idle, require complete30-armR1terminalaudit, prepare all1986real token/prefix templates and compare original/prototype on the two declared mainseed901ledger-derived histories. Check every recorded dispatch plus every16thlifecycleevent. Missing lock/wakeup/head-ID information remains explicit. No GPU, new inference, E2E/quality speedup or exactproductiondecisionreplay claim.')
    with path.open('x') as out:out.write(json.dumps(r,indent=2)+'\n')


def execute(path):
    path=Path(path);r=json.loads(path.read_text());output=path.with_suffix('.result.json')
    assert r['kind']=='real_prefix_ledger_state_validation_not_production_trace_replay' and not output.exists() and not path.with_suffix('.failure.json').exists()
    print('Waiting on exact CPU probe',r['after_pid'],flush=True);wait_parent(r);idle()
    assert sha(PARENT)==r['parent_registration_sha256'] and sha(FREEZE)==r['freeze_sha256']
    parent_path=PARENT.with_suffix('.result.json');parent=json.loads(parent_path.read_text())
    assert parent['complete'] is True and parent['synthetic'] is True and parent['gpu_execution'] is False and len(parent['cases'])==45
    for name,digest in r['source_sha256'].items():assert sha(name)==digest,name
    full=json.loads(FULL.read_text());assert full['complete'] is True and full['requests']==59580 and full['errors']==0
    assert full['unique_qa']==1986 and full['separate_warmup_requests']==1800 and len(full['runs'])==30 and full['freeze_sha256']==r['freeze_sha256']
    freeze=json.loads(FREEZE.read_text());assert all(importlib.metadata.version(n)==v for n,v in freeze['main_package_versions'].items())
    proof_paths=[p for p in freeze['preflight_artifact_sha256'] if p.endswith('_input_preflight.json')];assert len(proof_paths)==1
    pp=Path(proof_paths[0]);assert sha(pp)==freeze['preflight_artifact_sha256'][str(pp)]
    preflight=json.loads(pp.read_text());fp_path=Path(preflight['main_fingerprints_path']);assert sha(fp_path)==preflight['main_fingerprints_sha256']
    fingerprints=json.loads(fp_path.read_text());expected={p['request_id']:p for p in fingerprints['requests']};assert len(expected)==1986
    for name,digest in fingerprints['tokenizer_artifact_sha256'].items():assert sha(name)==digest,name
    by={p['run_id']:p for p in full['runs']};cells=[]
    for rid in r['target_run_ids']:
        ap=BASE/(rid+'.full_audit_r1.json');zp=BASE/(rid+'.archive_r1.json');sp=BASE/(rid+'.setup.json');a=json.loads(ap.read_text())
        assert sha(ap)==by[rid]['audit_sha256'] and sha(zp)==by[rid]['archive_sha256'] and sha(sp)==a['setup_sha256']
        assert a['complete'] is True and a['requests']==1986 and a['errors']==0
        settings=yaml.safe_load(json.loads(sp.read_text())['gateway_config']);cells.append((rid,ap,zp,a,settings))
    namespaces={(c[4]['model'],c[4]['scheduler']['block_size'],c[4]['scheduler']['min_shared_tokens']) for c in cells};assert len(namespaces)==1
    namespace,block_size,min_shared=next(iter(namespaces));model=get_model('qwen3-4b');assert namespace==model['path'] and model['revision']==freeze['model_revision']
    # Tokenization/hashing happens only in this post-study idle stage.
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(model['path'],local_files_only=True,trust_remote_code=False)
    source=Path(cells[0][3]['step']['trace']);assert sha(source)==freeze['input_file_sha256'][str(source)]
    templates={};plain=hashlib.sha256();canonical=CanonicalTraceDigest();total_tokens=0
    with gzip.open(source,'rb') as stream:
        for line in stream:
            plain.update(line);row=json.loads(line);canonical.update(row)
            ids,blocks,engine,_=prepare(tokenizer,row['prompt'],block_size,namespace,True);rid=row['request_id'];ref=expected[rid]
            assert len(ids)==row['input_tokens']==ref['input_tokens'] and row['max_tokens']==96 and len(ids)+96<=32768
            assert hashlib.sha256(row['prompt'].encode()).hexdigest()==ref['prompt_sha256']
            assert hashlib.sha256(struct.pack('<'+'I'*len(ids),*ids)).hexdigest()==ref['token_ids_u32le_sha256']
            assert rid not in templates
            templates[rid]=Ticket(request_id=rid,blocks=blocks,arrival_ns=0,enqueued_ns=0,deadline_ns=0,
                group=group_digest(blocks,min_shared_tokens=min_shared,block_size=block_size),engine_blocks=engine,input_tokens=len(ids),output_budget=96)
            total_tokens+=len(ids)
    assert len(templates)==1986 and total_tokens==50522325
    assert plain.hexdigest()==preflight['inputs'][str(source)]['uncompressed_sha256'] and canonical.hexdigest()==preflight['inputs'][str(source)]['canonical_sha256']
    results=[]
    for rid,ap,zp,a,settings in cells:
        idle()
        with expanded(zp) as archive:
            assert archive['audit_sha256']==sha(ap) and {p['path']:p['sha256'] for p in archive['files']}==a['raw_sha256']
            records=[json.loads(l) for l in (BASE/'raw'/(rid+'.gateway.jsonl')).read_text().splitlines()]
            assert len(records)==1986 and all(row['run_id']==rid and row['status']=='ok' for row in records)
            result=asyncio.run(compare_ledger_states(records,templates,settings,stride=r['event_stride'],polls=r['stable_polls']))
            results.append(dict(run_id=rid,audit_sha256=sha(ap),archive_sha256=sha(zp),result=result))
        print('Checked real-prefix ledger states',rid,flush=True)
    with output.open('x') as out:out.write(json.dumps(dict(complete_ledger_state_check=True,gpu_execution=False,production_decision_trace_reproduced=False,
        registration_sha256=sha(path),parent_result_sha256=sha(parent_path),terminal_full_audit_sha256=sha(FULL),source_trace_sha256=sha(source),
        unique_qa=1986,input_tokens=total_tokens,request_trajectories=3972,runs=results,
        scope='All real prompt/token/group/engine-block templates matched pinned preflight; original/prototype parity checked on the two declared ledger-derived main histories. Recorded dispatch/reservation disagreement, missing head/wakeup/lock-order information are retained. This is not exactproductiondecisiontrace replay, CPU timing, GPU behavior, quality equivalence, performance gain or completed research.'),indent=2)+'\n')
    print('Ledger-derived state checks complete; not GPU/E2E evidence',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('register');a.add_argument('pid',type=int);a.add_argument('output',type=Path)
    a=sub.add_parser('execute');a.add_argument('registration',type=Path);a=p.parse_args()
    if a.command=='register':register(a.pid,a.output);print('Registered ledger-state validation',a.output,flush=True)
    else:
        try:execute(a.registration)
        except Exception as exc:
            with a.registration.with_suffix('.failure.json').open('x') as out:out.write(json.dumps(dict(complete=False,error=repr(exc),scope='Preserved ledger-state validation failure; no serving modification or automatic retry'),indent=2)+'\n')
            raise
