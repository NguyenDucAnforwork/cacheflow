"""Explicit CPU-check revision; preserve original failed V7 gate unchanged.

The checker kernel is mechanically derived from the original function. Only
the declared prerequisite/identity/output labels change. All real-token and
two-history state comparisons remain intact. This never launches inference.
"""
import argparse
import ast
import copy
import hashlib
import json
import sys
from datetime import datetime,timezone
from pathlib import Path
import psutil
import v7_epoch_trace_check as parent
from v6_raw_archive import sha
from v6_regenerate_full_inputs import wait_parent,idle

BASE=Path('results/v3');REG=BASE/'v8_epoch_trace_revision_registration.json'
CHECKPOINT=BASE/'v6full1_checkpoint_10.json';FAILED=BASE/'v6full1_union_s902_terminal_failure.json'
DIAG=BASE/'v8diag1_registration.json';PROTOCOL=Path('docs/V8_EPOCH_TRACE_REVISION.md')
ORIGINAL=Path('scripts/v7_epoch_trace_check.py')
KIND='real_prefix_ledger_state_revision_after_failed_full_not_gpu'


def write(path,value):
    with Path(path).open('x') as f:f.write(json.dumps(value,indent=2)+'\n')


def revised_source():
    tree=ast.parse(ORIGINAL.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='execute')
    source=ast.get_source_segment(ORIGINAL.read_text(),fn)
    old="""    full=json.loads(FULL.read_text());assert full['complete'] is True and full['requests']==59580 and full['errors']==0
    assert full['unique_qa']==1986 and full['separate_warmup_requests']==1800 and len(full['runs'])==30 and full['freeze_sha256']==r['freeze_sha256']"""
    changes=[
        ("r['kind']=='real_prefix_ledger_state_validation_not_production_trace_replay'",f"r['kind']=='{KIND}'"),
        ("print('Waiting on exact CPU probe'","print('Revised CPU checker waiting on exact V8 diagnostic controller'"),
        (old,"    full=validate_failed_full_checkpoint(r)"),
        ("terminal_full_audit_sha256=sha(FULL)","checkpoint_sha256=sha(CHECKPOINT),original_full_attempt_failed=True"),
    ]
    for old,new in changes:
        assert source.count(old)==1,old
        source=source.replace(old,new,1)
    return source,dict(original_function_ast_sha256=hashlib.sha256(ast.dump(fn,include_attributes=False).encode()).hexdigest(),
        revised_function_ast_sha256=hashlib.sha256(ast.dump(ast.parse(source).body[0],include_attributes=False).encode()).hexdigest(),
        replacements=[dict(old=a,new=b) for a,b in changes],scope='Only prerequisite/registration identity/wait message/output provenance substitutions; tokenization, fingerprints, archive validation and compare_ledger_states unchanged.')


def validate_failed_full_checkpoint(r):
    for name,digest in r['evidence_sha256'].items():assert sha(name)==digest,name
    c=json.loads(CHECKPOINT.read_text());f=json.loads(FAILED.read_text())
    assert c['complete'] is False and c['kind']=='interim_full_checkpoint_not_terminal_audit'
    assert c['completed_arms']==10 and c['measured_requests']==19860 and c['unique_qa']==1986 and len(c['runs'])==10
    assert c['freeze_sha256']==r['freeze_sha256'] and c['separate_completed_warmup_requests']==600
    assert f['requests']==1986 and f['successes']==973 and f['errors']==1013 and f['performance_valid'] is False
    assert f['completed_full_arms']==10 and f['failed_full_arms']==1 and f['unexecuted_full_arms']==19
    assert {rid for rid in r['target_run_ids']}=={'v6full1-main-g6-union64-s901','v6full1-main-g6-packing_ready-s901'}
    by={cell['run_id']:cell for cell in c['runs']}
    for rid in r['target_run_ids']:
        cell=by[rid];assert cell['summary']['requests']==1986 and cell['summary']['errors']==0
        for suffix,key in [('.full_audit_r1.json','audit_sha256'),('.archive_r1.json','archive_sha256')]:assert sha(BASE/(rid+suffix))==cell[key]
    for name,flag in [('v6full1_input_regeneration_registration.result.json','complete'),('v6full1_r1_namespace_preparation_registration.result.json','complete_namespace_preparation')]:
        assert json.loads((BASE/name).read_text())[flag] is True
    return c


def register(pid):
    assert not REG.exists();p=psutil.Process(pid);argv=p.cmdline()
    assert p.is_running() and p.status()!=psutil.STATUS_ZOMBIE
    assert argv[-2:]==['scripts/v8_full_liveness_diagnostic.py','execute']
    original_reg=BASE/'v7_epoch_trace_check_registration.json';old=json.loads(original_reg.read_text())
    sources=old['source_sha256']|{str(ORIGINAL):sha(ORIGINAL),str(Path(__file__).resolve().relative_to(Path.cwd())):sha(__file__)}
    for name,digest in sources.items():assert sha(name)==digest,name
    source,transform=revised_source()
    evidence=[CHECKPOINT,FAILED,DIAG,original_reg,original_reg.with_suffix('.failure.json'),BASE/'v7dev1_epoch_after_trace_registration.failure.json',
        BASE/'v6full1_input_regeneration_registration.result.json',BASE/'v6full1_r1_namespace_preparation_registration.result.json',
        BASE/'v7_epoch_cpu_probe_registration.result.json']
    r=dict(kind=KIND,registered_utc=datetime.now(timezone.utc).isoformat(),after_pid=pid,after_create_time=p.create_time(),after_argv=argv,
        parent_registration_sha256=sha(parent.PARENT),freeze_sha256=old['freeze_sha256'],source_sha256=sources,
        evidence_sha256={str(p):sha(p) for p in evidence},protocol_sha256=sha(PROTOCOL),
        target_run_ids=old['target_run_ids'],event_stride=old['event_stride'],stable_polls=old['stable_polls'],
        transformation=transform,revised_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        scope='CPU parity check only, all1986real prefixes/two completed seed901histories3972trajectories. Original full failed10complete/1failed/19unexecuted, original V7 check/GPU gate failures retained. Wait for exact V8 diagnostic to terminate and all services idle; no GPU, retry or full-study success substitution.')
    validate_failed_full_checkpoint(r);write(REG,r);return r


def execute():
    r=json.loads(REG.read_text());assert r['kind']==KIND
    assert not REG.with_suffix('.result.json').exists() and not REG.with_suffix('.failure.json').exists()
    print('Revised CPU prefix checker queued after live diagnostic',r['after_pid'],flush=True);wait_parent(r);idle()
    assert sha(PROTOCOL)==r['protocol_sha256']
    validate_failed_full_checkpoint(r)
    terminal=BASE/'v8diag1_terminal.json';failure=BASE/'v8diag1_failure.json'
    assert terminal.exists() or failure.exists(),'Retain diagnostic terminal evidence before CPU work'
    source,transform=revised_source();assert transform==r['transformation'] and hashlib.sha256(source.encode()).hexdigest()==r['revised_source_sha256']
    scope=dict(vars(parent),validate_failed_full_checkpoint=validate_failed_full_checkpoint,CHECKPOINT=CHECKPOINT)
    exec(compile(source,str(Path(__file__))+'::explicit_revision','exec'),scope)
    scope['execute'](REG)


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('register');c.add_argument('pid',type=int);sub.add_parser('execute');a=p.parse_args()
    if a.command=='register':register(a.pid);print('Registered explicit real-prefix revision',REG,flush=True)
    else:
        try:execute()
        except Exception as exc:
            out=REG.with_suffix('.failure.json')
            if not out.exists():write(out,dict(complete=False,error=repr(exc),scope='Retained CPU revision failure; no GPU, retry or original V7 gate modification.'))
            raise
