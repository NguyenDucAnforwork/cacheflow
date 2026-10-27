"""Shared native intervention and offline request-window checks for V10.

Identity is observed at connector construction, then checked for unchanged
proofs/PID/birth around replay. It is not a per-request live-code RPC.
"""
import json
from pathlib import Path
import psutil
from v6_raw_archive import sha
from v9_native_identity import identity,SOURCE

BASE=Path('results/v3')


def validate_repair(audit,terminal,registration):
    """Require the entire independently audited diagnostic, retaining failed full arms."""
    from v9_repair_r1 import plan,REG,verify
    verify(registration)
    assert audit['complete_repair_diagnostic_audit'] is True
    assert audit['performance_valid'] is False and audit['research_complete'] is False
    assert audit['registration_sha256']==terminal['registration_sha256']==sha(REG)
    assert audit['terminal_sha256']==sha(BASE/'v9repair2_terminal.json')
    assert terminal['diagnostic_execution_complete'] is True and terminal['error'] is None and terminal['cleanup_errors']==[]
    assert audit['target_requests']==8064 and audit['separate_warmups']==360
    assert audit['distinct_engines']==audit['distinct_cpu_caches']==6
    expected=plan();runs=audit['runs'];outcomes=terminal['outcomes']
    assert len(runs)==len(outcomes)==len(expected)==6
    for row,outcome,step in zip(runs,outcomes,expected):
        assert row['run_id']==outcome['run_id']==step['run_id']
        assert row['requests']==outcome['requests']==step['requests'] and row['errors']==outcome['errors']>=0
        path=BASE/(step['run_id']+'.repair_audit.json')
        assert sha(path)==row['audit_sha256']==outcome['audit_sha256']
        detail=json.loads(path.read_text());assert detail['step']==step
        if row['errors']==0:
            assert detail['quality_sha256']==row['quality_sha256']==sha(BASE/(step['run_id']+'.quality.json'))
        else:
            assert step['stage']=='full' and detail['quality_sha256'] is row['quality_sha256'] is None
        if step['probe']:
            assert row['errors']==0
            probe=row['probe'];assert probe==detail['probe'] and probe['eligible_sampled_prefetch_states']>0
            assert probe['distinct_inflated_ids']==0 if step['mode']=='idempotent' else probe['distinct_inflated_ids']>0
        else:assert row['probe'] is None
    assert len(audit['full_pairs'])==2 and {p['seed'] for p in audit['full_pairs']}=={901,902}
    for pair in audit['full_pairs']:
        assert (pair['quality_and_work_comparison'] is not None)==(pair['reference_errors']==pair['idempotent_errors']==0)
        assert pair['reference_errors']==next(r['errors'] for r in runs if r['run_id']==pair['reference'])
        assert pair['idempotent_errors']==next(r['errors'] for r in runs if r['run_id']==pair['idempotent'])


def engine_config(original,step,freeze):
    root=Path.cwd();old=f'command={root}/scripts/v2_serve_vllm.sh'
    assert original.count(old)==1 and original.count('environment=')==1
    assert step['engine']=='main' and step['mode']=='idempotent' and step['probe'] is False
    assert step['proof_label']==step['run_id']+'-native'
    fields=dict(CACHEFLOW_V9_WATERMARK_MODE='idempotent',
        CACHEFLOW_V9_WATERMARK_PROOF=str(root/BASE/'raw'/step['proof_label']),
        CACHEFLOW_V9_EXPECTED_CONNECTOR_SHA=freeze['repair_native_source_sha256'][str(SOURCE)],
        CACHEFLOW_V9_ENGINE_LOG=str(root/BASE/'raw'/(step['run_id']+'-engine.log')),
        CACHEFLOW_V9_ENABLE_PROBE='0')
    assert not any(key in original for key in fields),'Native options already injected'
    return original.replace(old,f'command=/bin/bash {root}/scripts/v9_serve_vllm.sh').replace(
        'environment=','environment='+','.join(k+'="'+v+'"' for k,v in fields.items())+',',1)


def capture_identity(step,freeze):
    from v4_services import service_pid
    p=psutil.Process(service_pid('cacheflow_v2_vllm'))
    return identity(step,dict(pid=p.pid,birth=p.create_time()),freeze)


def validate_identity(step,record,requests,freeze):
    before,after=record['before'],record['after']
    assert step['mode']=='idempotent' and step['probe'] is False and requests
    assert before['mode']==after['mode']=='idempotent' and before['end_identity_verified'] and after['end_identity_verified']
    assert before['engine_pid']==after['engine_pid']>0 and before['engine_birth']==after['engine_birth']
    assert before['checked_monotonic_ns']<min(row['client_send_ns'] for row in requests)
    assert after['checked_monotonic_ns']>max(row['complete_ns'] for row in requests)
    assert before['constructor_records']==after['constructor_records'] and before['proof_sha256']==after['proof_sha256']
    expected=freeze['native_method_expected']['idempotent'];proof_prefix=Path.cwd()/BASE/'raw'/step['proof_label']
    on_disk=[]
    assert before['proof_sha256'],'No actual constructor proof files'
    for name,digest in before['proof_sha256'].items():
        p=Path(name);assert p.parent==proof_prefix.parent and p.name.startswith(proof_prefix.name+'.') and p.name.endswith('.jsonl')
        assert sha(p)==digest
        on_disk.extend(json.loads(line) for line in p.read_text().splitlines())
    # Sort only for cross-file traversal; within-file exact records remain hashed.
    assert sorted(on_disk,key=lambda r:(r['pid'],r['monotonic_ns'],r['connector_role']))==sorted(before['constructor_records'],key=lambda r:(r['pid'],r['monotonic_ns'],r['connector_role']))
    assert {r['connector_role'] for r in on_disk}=={'KVConnectorRole.SCHEDULER','KVConnectorRole.WORKER'}
    for row in on_disk:
        assert row['connector_class']=='lmcache.integration.vllm.lmcache_mp_connector.LMCacheMPConnector'
        assert row['monotonic_ns']<before['checked_monotonic_ns']
        for key,value in expected.items():assert row[key]==value,key
    return True
