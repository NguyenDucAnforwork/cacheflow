"""V6 replay with explicit native identity and retained diagnostic failures."""
import ast
import hashlib
import json
import os
from pathlib import Path
from types import FunctionType
import psutil
import v8_diagnostic_capture as base
from v8_diag3_capture import bookends
from v9_native_identity import identity
from v6_raw_archive import sha


def process(service):
    record=base.process(service);p=psutil.Process(record['pid'])
    record['env'].update({k:v for k,v in p.environ().items() if k.startswith('CACHEFLOW_V9_')})
    return record


def capture_source():
    text=Path('scripts/v8_diagnostic_capture.py').read_text();fn=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='capture')
    source=ast.get_source_segment(text,fn)
    changes=[("rid.startswith('v8diag1-')","rid.startswith('v9repair2-')"),("BASE/'v8diag1_registry.csv'","BASE/'v9repair2_registry.csv'"),
        ("    for name,old in [('cacheflow_v2_vllm',engine),('cacheflow_v2_lmcache',lmcache),('cacheflow_v2_gateway',gateway)]:\n        now=process(name);assert now['pid']==old['pid'] and now['birth']==old['birth'] and now['argv']==old['argv']",
         "    end_summary=json.loads(raw.with_suffix('.summary.json').read_text())\n    process_bookends=bookends([('cacheflow_v2_vllm',engine),('cacheflow_v2_lmcache',lmcache),('cacheflow_v2_gateway',gateway)],end_summary)"),
        ("status_counts=statuses,gateway_closed_records=len(gateway_rows)","status_counts=statuses,process_bookends=process_bookends,gateway_closed_records=len(gateway_rows)"),
        ('V8 liveness diagnostic only;600s timeouts.','V9 native repair diagnostic only;600s timeouts.')]
    for old,new in changes:assert source.count(old)==1,old;source=source.replace(old,new,1)
    return source,dict(parent_source_sha256=sha('scripts/v8_diagnostic_capture.py'),changes=[dict(old=a,new=b) for a,b in changes],
        effective_ast_sha256=hashlib.sha256(ast.dump(ast.parse(source),include_attributes=False).encode()).hexdigest())


def capture(step,registration_path):
    reg=json.loads(Path(registration_path).read_text());engine=process('cacheflow_v2_vllm');before=identity(step,engine,reg)
    source,_=capture_source();scope=dict(vars(base),__file__=__file__,process=process,bookends=bookends)
    exec(compile(source,str(Path(__file__))+'::explicit_repair_capture','exec'),scope)
    result=scope['capture'](step,sha(registration_path))
    try:after=identity(step,engine,reg)
    except (psutil.NoSuchProcess,AssertionError):
        assert result['errors']>0 and not psutil.pid_exists(engine['pid']),'Native identity lost without an absent failed engine'
        after=dict(engine_pid=engine['pid'],engine_birth=engine['birth'],mode=step['mode'],end_identity_verified=False)
    if after['end_identity_verified']:
        assert before['proof_sha256']==after['proof_sha256'] and before['constructor_records']==after['constructor_records'],'Native instances/method identity changed during replay'
    raw=Path('results/v3/raw')/(step['run_id']+'.jsonl');rows=[json.loads(l) for l in raw.read_text().splitlines()]
    assert max(r['complete_ns'] for r in rows)>min(r['client_send_ns'] for r in rows)>before['checked_monotonic_ns']
    if after['end_identity_verified']:assert after['checked_monotonic_ns']>max(r['complete_ns'] for r in rows)
    path=Path('results/v3')/(step['run_id']+'.native_identity.json')
    base.write(path,dict(before=before,after=after,registration_sha256=sha(registration_path),setup_sha256=sha(Path('results/v3')/(step['run_id']+'.diagnostic_setup.json')),
        scope='Native constructor/effective-code bookends bracket actual client ledger. Failed missing end identity is explicit; no quality, liveness or performance conclusion.'))
    return dict(result,native_identity_sha256=sha(path))
