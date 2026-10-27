"""Independent single full diagnostic checkpoint; no cross-seed/latency claim."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from v6_raw_archive import sha
from v6_main_resources import analyze
from v7_observe_full_liveness import parsed_lines
from v8_diagnostic_capture import check_rows
from v9_repair_r1 import REG,verify

BASE=Path('results/v3');RAW=BASE/'raw'


def checkpoint(run_id,output):
    output=Path(output);assert not output.exists();read=lambda p:json.loads(Path(p).read_text())
    reg=read(REG);verify(reg);step=next(s for s in reg['actions'] if s['run_id']==run_id)
    assert step['stage']=='full' and step['probe'] is False
    ap=BASE/(run_id+'.repair_audit.json');a=read(ap);outcome=read(BASE/(run_id+'.outcome.json'))
    assert a['step']==step and a['registration_sha256']==sha(REG) and outcome['audit_sha256']==sha(ap)
    assert a['diagnostic_integrity_checked'] and a['performance_valid'] is False and a['probe'] is None
    pre=read(BASE/'v6full1_input_preflight.json');fp=Path(pre['main_fingerprints_path']);assert sha(fp)==pre['main_fingerprints_sha256']
    metadata=[ap,fp,REG];target_rows=None;target_summary=None
    for warm in [True,False]:
        current=run_id+'-warm' if warm else run_id
        setup_path=BASE/(current+'.diagnostic_setup.json');setup=read(setup_path)
        ip=BASE/(current+'.diagnostic_integrity.json');integrity=read(ip)
        np=BASE/(current+'.native_identity.json');native=read(np);metadata+=[setup_path,ip,np]
        assert integrity['registration_sha256']==native['registration_sha256']==setup['registration_sha256']==sha(REG)
        assert integrity['setup_sha256']==native['setup_sha256']==sha(setup_path)
        for name,digest in integrity['raw_sha256'].items():assert sha(name)==digest,name
        summary=read(RAW/(current+'.summary.json'));assert summary['requests']==summary['successes']==(60 if warm else 1986) and summary['errors']==0
        assert summary['engine_pid']==setup['engine']['pid'] and summary['lmcache_pid']==setup['lmcache']['pid']
        assert summary['request_read_timeout_s']==summary['request_pool_timeout_s']==600 and summary['client_keepalive_connections']==0
        rows=parsed_lines((RAW/(current+'.jsonl')).read_bytes());outputs=parsed_lines((RAW/(current+'.outputs.jsonl')).read_bytes())
        if warm:
            import hashlib
            expected={r['request_id']:dict(r,prompt_sha256=hashlib.sha256(r['prompt'].encode()).hexdigest()) for r in parsed_lines(Path('data/processed/v3/v5-dev4b3-qps4-s101.jsonl').read_bytes())}
        else:expected={r['request_id']:r for r in read(fp)['requests']}
        assert check_rows(rows,outputs,expected,current)=={'ok':len(expected)}
        assert len(rows)==summary['requests']
        assert all(r['scheduled_arrival_ns']<=r['client_send_ns']<=r['first_token_ns']<=r['complete_ns'] for r in rows)
        before,after=native['before'],native['after']
        assert before['mode']==after['mode']==step['mode'] and after['end_identity_verified']
        assert before['engine_pid']==after['engine_pid']==summary['engine_pid'] and before['engine_birth']==after['engine_birth']==setup['engine']['birth']
        assert before['checked_monotonic_ns']<min(r['client_send_ns'] for r in rows) and after['checked_monotonic_ns']>max(r['complete_ns'] for r in rows)
        assert before['constructor_records']==after['constructor_records'] and before['proof_sha256']==after['proof_sha256']
        assert {r['connector_role'] for r in before['constructor_records']}=={'KVConnectorRole.SCHEDULER','KVConnectorRole.WORKER'}
        for row in before['constructor_records']:
            for key,value in reg['native_method_expected'][step['mode']].items():assert row[key]==value,key
        for name,digest in before['proof_sha256'].items():assert sha(name)==digest,name
        if not warm:
            assert a['result']==dict(integrity,native_identity_sha256=sha(np));target_rows=rows;target_summary=summary
    resource=analyze(parsed_lines((RAW/(run_id+'.metrics.jsonl')).read_bytes()));assert resource==a['resources']
    counter=resource['strict_counter_deltas']['vllm'];assert counter['vllm:prompt_tokens_total']==sum(r['input_tokens'] for r in target_rows)==50522325
    assert counter['vllm:prompt_tokens_cached_total']+counter['vllm:request_prefill_kv_computed_tokens_sum']==50522325
    qp=BASE/(run_id+'.quality.json');assert sha(qp)==a['quality_sha256'];metadata.append(qp)
    with tempfile.TemporaryDirectory(prefix='cacheflow-v9-full-check-') as folder:
        target=Path(folder)/'quality.json';subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir',str(RAW),'--run-ids',run_id,'--output',str(target)],check=True,stdout=subprocess.DEVNULL)
        assert read(target)==read(qp),'Official quality recomputation differs'
    q=read(qp)['runs'][0];assert q['answerable_n']==1540 and q['by_category']['5']['n']==446 and len(q['per_request'])==1986
    assert sha(a['engine_log_path'])==a['engine_log_sha256']
    result=dict(kind='independent_complete_single_full_repair_checkpoint',run_id=run_id,mode=step['mode'],requests=1986,errors=0,separate_warmups=60,
        complete_single_diagnostic_check=True,complete_six_arm_study=False,performance_valid=False,research_complete=False,
        finished_utc=target_summary['finished_utc'],answerable_f1=q['answerable_f1'],category5=q['by_category']['5'],output_budget_hits=q['output_budget_hits'],
        new_prefill=counter['vllm:request_prefill_kv_computed_tokens_sum'],external_consumed=counter['vllm:prompt_tokens_source_external_kv_transfer_total'],preemptions=counter['vllm:num_preemptions_total'],
        metadata_sha256={str(p):sha(p) for p in metadata},raw_sha256=a['result']['raw_sha256']|{a['engine_log_path']:a['engine_log_sha256']},auditor_source_sha256=sha(__file__),
        scope='Whole successful full diagnostic plus separate warmup reopened; source/native-code/PID/proof/clock continuity and official quality recomputed. No same-seed comparison, latency speedup, quality equivalence, stall fix, six-arm completion or competitive contribution claim. Failure of another seed remains retained.')
    with output.open('x') as out:out.write(json.dumps(result,indent=2)+'\n')
    print('Independent full diagnostic check',run_id,'F1',q['answerable_f1'],'category5',q['by_category']['5'],'prefill',result['new_prefill'],flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument('output',type=Path);a=p.parse_args();checkpoint(a.run_id,a.output)
