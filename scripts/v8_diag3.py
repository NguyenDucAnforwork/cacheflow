"""Retain failed V8diag1; prospectively run only its unexecuted on/offB phases."""
import argparse
import ast
import copy
import hashlib
import json
import subprocess
from types import FunctionType
from datetime import datetime,timezone
from pathlib import Path
import psutil
import v8_full_liveness_diagnostic as original
from v6_regenerate_full_inputs import wait_parent,idle
from v6_raw_archive import sha
from v8_diag3_capture import capture,capture_source

BASE=Path('results/v3');PREFIX='v8diag3';REG=BASE/(PREFIX+'_registration.json')
PROTOCOL=Path('docs/V8_DIAGNOSTIC_NAMESPACE_BINDING_R1.md')
CPU=BASE/'v8_epoch_trace_revision_registration.json'


def write(path,value):
    with Path(path).open('x') as f:f.write(json.dumps(value,indent=2)+'\n')


def write_configs(r,phase):
    root=Path.cwd()
    for name,path in original.CONFIGS.items():
        text=r['config_original'][name]
        if name.endswith('gateway'):text=text.replace(f'command={root}/scripts/v2_serve_gateway.sh',f'command={root}/scripts/v6_serve_gateway.sh')
        else:
            text=text.replace(f'command={root}/scripts/v2_serve_vllm.sh',f'command=/bin/bash {root}/scripts/v8_diag3_serve_vllm.sh')
            env=f'environment=CACHEFLOW_V8_ENGINE_LOG="{root}/results/v3/raw/{PREFIX}-{phase}.engine.log",'
            if phase=='on':env+=f'CACHEFLOW_V8_LIVENESS_LOG="{root}/results/v3/raw/{PREFIX}-probe",'
            text=text.replace('environment=',env,1)
        path.write_text(text)


def controller_source():
    path=Path('scripts/v8_full_liveness_diagnostic.py');text=path.read_text();tree=ast.parse(text)
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='execute');source=ast.get_source_segment(text,fn)
    start=source.index('            for n,p in CONFIGS.items():');end=source.index('            update()',start)
    block=source[start:end]
    changes=[("for phase in ['offA','on','offB']:","for phase in ['on','offB']:"),
        (block,'            write_configs(r,phase)\n'),('len(outcomes)==6','len(outcomes)==4')]
    for old,new in changes:
        assert source.count(old)==1,old;source=source.replace(old,new,1)
    return source,dict(parent_source_sha256=sha(path),changes=[dict(old=a,new=b) for a,b in changes],
        derived_function_ast_sha256=hashlib.sha256(ast.dump(ast.parse(source).body[0],include_attributes=False).encode()).hexdigest(),
        scope='Only fixed unexecuted phases, uniform engine logging wrapper and expected action count differ. Original stop/cleanup/restore/probe coverage/config/model/source checks unchanged.')


def idle_gpu():
    idle()
    values=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True)
    assert all(int(v.strip())<1024 for v in values.splitlines()),'GPU still occupied before a fresh diagnostic phase'


def cpu_terminal():
    for p in psutil.process_iter(['cmdline','status']):
        argv=p.info['cmdline'] or []
        assert p.info['status']==psutil.STATUS_ZOMBIE or not ('scripts/v8_epoch_trace_revision.py' in argv and 'execute' in argv),'CPU checker remains live'


def register(pid=None):
    assert not REG.exists()
    if pid is not None:
        p=psutil.Process(pid);argv=p.cmdline()
        assert p.is_running() and p.status()!=psutil.STATUS_ZOMBIE and argv[-2:]==['scripts/v8_epoch_trace_revision.py','execute']
        parent=dict(wait_mode='live_exact_parent',after_pid=pid,after_create_time=p.create_time(),after_argv=argv)
    else:
        cpu_terminal();result=CPU.with_suffix('.result.json');proof=json.loads(result.read_text());assert proof['complete_ledger_state_check'] is True and proof['gpu_execution'] is False
        parent=dict(wait_mode='already_terminal_verified_process_scan',cpu_revision_result_sha256=sha(result))
    old_path=BASE/'v8diag1_registration.json';old=json.loads(old_path.read_text())
    for group in ['source_sha256','native_source_sha256']:
        for name,digest in old[group].items():assert sha(name)==digest,name
    terminal=BASE/'v8diag1_terminal.json';t=json.loads(terminal.read_text());assert t['diagnostic_execution_complete'] is False and t['cleanup_errors']==[] and len(t['outcomes'])==1
    post=BASE/'v8diag1_offA_postmortem_integrity.json';f=json.loads(post.read_text());assert f['requests']==1986 and f['successes']==423 and f['errors']==1563
    idle_gpu()
    _,ct=controller_source();_,pt=capture_source();r=copy.deepcopy(old)
    r.update(kind='explicit_remaining_on_offB_after_engine_exit_collector_amendment',registered_utc=datetime.now(timezone.utc).isoformat(),
        **parent,
        protocol_sha256=sha(PROTOCOL),controller_transformation=ct,capture_transformation=pt,
        actions=[dict(s,run_id=s['run_id'].replace('v8diag1-','v8diag3-')) for s in old['actions'] if s['phase'] in {'on','offB'}],
        amendment_evidence_sha256={str(n):sha(n) for n in [old_path,terminal,BASE/'v8diag1_failure.json',post,CPU,BASE/'v8_native_hol_hypothesis_registration.json',BASE/'v8diag2_registration.json',BASE/'v8diag2_failure.json',Path('docs/V8_DIAGNOSTIC_ENGINE_EXIT_AMENDMENT.md')]},
        scope='Two unexecuted diagnostic phases only, on/offB; original offA failure retained, no retry or claim that original off/on/off completed. Same full input/settings/600s transport. Only post-replay accounting permits a missing original engine with client errors; both phases uniformly preserve native stderr/stdout. All outcomes diagnostic, no functional native patch or performance claim.')
    extra=['scripts/v8_diag3.py','scripts/v8_diag3_capture.py','scripts/v8_diag3_serve_vllm.sh']
    r['source_sha256'].update({n:sha(n) for n in extra})
    for name,path in original.CONFIGS.items():assert path.read_text()==r['config_original'][name]
    assert not list((BASE/'raw').glob('v8diag1-probe.*.jsonl')),'No original on phase may have started'
    write(REG,r);return r


def controller_scope():
    scope=dict(vars(original),REG=REG,PREFIX=PREFIX,PROTOCOL=PROTOCOL,capture=capture,idle=idle_gpu,write_configs=write_configs)
    # Copied functions otherwise retain the ORIGINAL module's globals. Rebind
    # helpers that read protocol/PREFIX, so checks apply to this namespace.
    for name in ['verify_pins','probe_coverage']:
        fn=getattr(original,name)
        scope[name]=FunctionType(fn.__code__,scope,name,fn.__defaults__,fn.__closure__)
    return scope


def execute():
    r=json.loads(REG.read_text());assert r['kind']=='explicit_remaining_on_offB_after_engine_exit_collector_amendment'
    if r['wait_mode']=='live_exact_parent':
        print('V8 amended diagnostic waiting on exact CPU revision',r['after_pid'],flush=True);wait_parent(r)
    else:assert sha(CPU.with_suffix('.result.json'))==r['cpu_revision_result_sha256']
    cpu_terminal();idle_gpu()
    assert CPU.with_suffix('.result.json').exists() or CPU.with_suffix('.failure.json').exists(),'CPU revision terminal evidence missing'
    for name,digest in r['amendment_evidence_sha256'].items():assert sha(name)==digest,name
    source,ct=controller_source();_,pt=capture_source();assert ct==r['controller_transformation'] and pt==r['capture_transformation']
    scope=controller_scope()
    exec(compile(source,str(Path(__file__))+'::explicit_remaining_phases','exec'),scope)
    scope['execute']()


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('register');c.add_argument('--after-pid',type=int);sub.add_parser('execute');a=p.parse_args()
    if a.command=='register':register(a.after_pid);print('Registered amended remaining phases',REG,flush=True)
    else:
        try:execute()
        except Exception as exc:
            out=BASE/(PREFIX+'_failure.json')
            if not out.exists():write(out,dict(complete=False,error=repr(exc),scope='Retained amendment failure; no automatic retry.'))
            raise
