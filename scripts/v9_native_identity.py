"""Prospective code fingerprints and actual constructor proof validation."""
import ast
import hashlib
import json
import time
from pathlib import Path
from types import CodeType
import psutil
from cacheflow.v9_lookup_watermark import corrected_node,code_record,method_node
from v6_raw_archive import sha

SOURCE=Path('/venv/main/lib/python3.12/site-packages/lmcache/integration/vllm/lmcache_mp_connector.py')


def digest(code):return hashlib.sha256(json.dumps(code_record(code),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def expected():
    text=SOURCE.read_text();tree=compile(text,str(SOURCE),'exec')
    cls=next(c for c in tree.co_consts if isinstance(c,CodeType) and c.co_name=='LMCacheMPConnector')
    native=next(c for c in cls.co_consts if isinstance(c,CodeType) and c.co_name=='get_num_new_matched_tokens')
    node,proof=corrected_node(text);module=ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[]))
    compiled=compile(module,str(SOURCE)+'::cacheflow_v9_idempotent','exec');fixed=next(c for c in compiled.co_consts if isinstance(c,CodeType) and c.co_name=='get_num_new_matched_tokens')
    common=dict(native_source_path=str(SOURCE),native_source_sha256=sha(SOURCE),installer_source_sha256=sha('src/cacheflow/v9_lookup_watermark.py'),
        original_method_code_sha256=digest(native),original_method_ast_sha256=proof['original_method_ast_sha256'],code_fingerprint_version=1)
    return {mode:dict(common,mode=mode,effective_method_code_sha256=digest(fn),effective_method_ast_sha256=proof['effective_method_ast_sha256'] if mode=='idempotent' else proof['original_method_ast_sha256'],functional_replacements=int(mode=='idempotent')) for mode,fn in [('reference',native),('idempotent',fixed)]}


def identity(step,engine,registration):
    p=psutil.Process(engine['pid']);assert p.is_running() and p.status()!=psutil.STATUS_ZOMBIE and p.create_time()==engine['birth']
    env=p.environ();assert env.get('CACHEFLOW_V9_WATERMARK_MODE')==step['mode'] and env.get('CACHEFLOW_V9_ENABLE_PROBE')==str(int(step['probe']))
    assert bool(env.get('CACHEFLOW_V8_LIVENESS_LOG'))==step['probe'] and not env.get('CACHEFLOW_VLLM_LIVENESS_LOG')
    family={p.pid}|{c.pid for c in p.children(recursive=True)};prefix=env['CACHEFLOW_V9_WATERMARK_PROOF']
    assert prefix==str(Path.cwd()/'results/v3/raw'/step['proof_label'])
    files=sorted(Path(prefix).parent.glob(Path(prefix).name+'.*.jsonl'));assert files,'No actual native constructor proof'
    records=[]
    for path in files:
        for line in path.read_text().splitlines():
            row=json.loads(line);assert row['pid'] in family,'Proof is not from current engine family'
            for key,value in registration['native_method_expected'][step['mode']].items():assert row[key]==value,(key,row[key],value)
            assert row['connector_class']=='lmcache.integration.vllm.lmcache_mp_connector.LMCacheMPConnector'
            records.append(row)
    assert {row['connector_role'] for row in records}=={'KVConnectorRole.SCHEDULER','KVConnectorRole.WORKER'}
    return dict(engine_pid=p.pid,engine_birth=p.create_time(),constructor_records=records,proof_sha256={str(path):sha(path) for path in files},
        checked_monotonic_ns=time.monotonic_ns(),mode=step['mode'],end_identity_verified=True)
