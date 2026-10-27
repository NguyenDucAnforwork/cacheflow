"""Explicit post-replay-only collector amendment; failed engine exit is evidence."""
import ast
import hashlib
import json
from pathlib import Path
import v8_diagnostic_capture as original


def bookends(before,summary):
    records={}
    for name,old in before:
        pid=original.service_pid(name)
        if pid==0:
            assert name=='cacheflow_v2_vllm' and summary['errors']>0,'Missing process without a failed engine attempt'
            records[name]=dict(original_pid=old['pid'],original_birth=old['birth'],end_state='engine_absent_after_failed_replay',end_identity_verified=False)
        else:
            now=original.process(name)
            assert now['pid']==old['pid'] and now['birth']==old['birth'] and now['argv']==old['argv'],'Serving process replaced'
            records[name]=dict(original_pid=old['pid'],original_birth=old['birth'],end_state='same_process',end_identity_verified=True)
    return records


def capture_source():
    path=Path('scripts/v8_diagnostic_capture.py');text=path.read_text();tree=ast.parse(text)
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='capture');source=ast.get_source_segment(text,fn)
    changes=[
        ("rid.startswith('v8diag1-')","rid.startswith('v8diag2-')"),
        ("BASE/'v8diag1_registry.csv'","BASE/'v8diag2_registry.csv'"),
        ("    for name,old in [('cacheflow_v2_vllm',engine),('cacheflow_v2_lmcache',lmcache),('cacheflow_v2_gateway',gateway)]:\n        now=process(name);assert now['pid']==old['pid'] and now['birth']==old['birth'] and now['argv']==old['argv']",
         "    end_summary=json.loads(raw.with_suffix('.summary.json').read_text())\n    process_bookends=bookends([('cacheflow_v2_vllm',engine),('cacheflow_v2_lmcache',lmcache),('cacheflow_v2_gateway',gateway)],end_summary)"),
        ("status_counts=statuses,gateway_closed_records=len(gateway_rows)","status_counts=statuses,process_bookends=process_bookends,gateway_closed_records=len(gateway_rows)"),
    ]
    for old,new in changes:
        assert source.count(old)==1,old;source=source.replace(old,new,1)
    return source,dict(parent_source_sha256=hashlib.sha256(text.encode()).hexdigest(),changes=[dict(old=a,new=b) for a,b in changes],
        derived_function_ast_sha256=hashlib.sha256(ast.dump(ast.parse(source).body[0],include_attributes=False).encode()).hexdigest(),
        scope='Only namespace/registry and post-replay failed-engine bookend accounting differ. All replay args, timeouts, metric capture, request/output/prompt checks unchanged; no request retry/native patch.')


def capture(step,registration_sha256):
    source,_=capture_source();scope=dict(vars(original),__file__=__file__,bookends=bookends)
    exec(compile(source,str(Path(__file__))+'::explicit_capture_amendment','exec'),scope)
    return scope['capture'](step,registration_sha256)
