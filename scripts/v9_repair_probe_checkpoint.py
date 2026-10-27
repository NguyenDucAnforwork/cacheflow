"""Reopen only the two completed probe arms; never claim six-arm completion."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from v6_raw_archive import sha
from v7_observe_full_liveness import parsed_lines
from v9_repair_r1 import BASE,REG,plan,probe_audit,verify


def main():
    out=BASE/'v9repair2_probe_checkpoint.json';assert not out.exists();r=json.loads(REG.read_text());verify(r)
    runs=[];requests={};scores={};engines=[];caches=[]
    for step in plan()[:2]:
        rid=step['run_id'];ap=BASE/(rid+'.repair_audit.json');a=json.loads(ap.read_text());assert a['step']==step and a['result']['requests']==60 and a['result']['errors']==0
        assert a['registration_sha256']==sha(REG) and a['diagnostic_integrity_checked'] and not a['performance_valid']
        probe=probe_audit(step,r);assert probe==a['probe'] and probe['eligible_sampled_prefetch_states']>0
        if step['mode']=='idempotent':assert probe['distinct_inflated_ids']==0
        else:assert probe['distinct_inflated_ids']>0
        for suffix in ['-warm','']:
            current=rid+suffix;metadata=json.loads((BASE/(current+'.diagnostic_integrity.json')).read_text())
            assert metadata['successes']==metadata['requests']==60 and metadata['errors']==0
            for name,digest in metadata['raw_sha256'].items():assert sha(name)==digest,name
            setup_path=BASE/(current+'.diagnostic_setup.json');setup=json.loads(setup_path.read_text());identity_path=BASE/(current+'.native_identity.json');identity=json.loads(identity_path.read_text())
            assert setup['registration_sha256']==identity['registration_sha256']==metadata['registration_sha256']==sha(REG)
            assert metadata['setup_sha256']==identity['setup_sha256']==sha(setup_path)
            before=identity['before'];after=identity['after'];assert after['end_identity_verified'] and before['proof_sha256']==after['proof_sha256']
            for name,digest in before['proof_sha256'].items():assert sha(name)==digest
            assert {p['connector_role'] for p in before['constructor_records']}=={'KVConnectorRole.WORKER','KVConnectorRole.SCHEDULER'}
            for proof in before['constructor_records']:
                for key,value in r['native_method_expected'][step['mode']].items():assert proof[key]==value,key
            rows=parsed_lines((BASE/'raw'/(current+'.jsonl')).read_bytes())
            assert before['checked_monotonic_ns']<min(row['client_send_ns'] for row in rows) and after['checked_monotonic_ns']>max(row['complete_ns'] for row in rows)
            if suffix=='':
                engines.append((setup['engine']['pid'],setup['engine']['birth']));caches.append((setup['lmcache']['pid'],setup['lmcache']['birth']))
                assert a['result']==dict(metadata,native_identity_sha256=sha(identity_path));requests[step['mode']]={row['request_id']:row for row in rows}
        qp=BASE/(rid+'.quality.json');assert sha(qp)==a['quality_sha256']
        with tempfile.TemporaryDirectory(prefix='cacheflow-v9-probe-grade-') as directory:
            check=Path(directory)/'quality.json'
            subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir',str(BASE/'raw'),'--run-ids',rid,'--output',str(check)],check=True,stdout=subprocess.DEVNULL)
            assert json.loads(check.read_text())==json.loads(qp.read_text())
        q=json.loads(qp.read_text())['runs'][0];assert q['answerable_n']==60 and len(q['per_request'])==60
        scores[step['mode']]={row['request_id']:row for row in q['per_request']}
        counter=a['resources']['strict_counter_deltas']['vllm']
        assert counter['vllm:prompt_tokens_total']==sum(row['input_tokens'] for row in requests[step['mode']].values())
        assert counter['vllm:prompt_tokens_cached_total']+counter['vllm:request_prefill_kv_computed_tokens_sum']==counter['vllm:prompt_tokens_total']
        runs.append(dict(run_id=rid,mode=step['mode'],audit_sha256=sha(ap),quality_sha256=sha(qp),probe=probe,
            answerable_f1=q['answerable_f1'],category5=q['by_category'].get('5'),output_budget_hits=q['output_budget_hits'],
            new_prefill=counter['vllm:request_prefill_kv_computed_tokens_sum'],external_consumed=counter['vllm:prompt_tokens_source_external_kv_transfer_total']))
    assert len(set(engines))==len(set(caches))==2
    a=requests['reference'];b=requests['idempotent'];assert a.keys()==b.keys() and len(a)==60
    assert all(a[k]['prompt_sha256']==b[k]['prompt_sha256'] and a[k]['input_tokens']==b[k]['input_tokens'] for k in a)
    aq=scores['reference'];bq=scores['idempotent'];assert aq.keys()==bq.keys()==a.keys()
    result=dict(complete_two_arm_probe_check=True,complete_six_arm_study=False,performance_valid=False,research_complete=False,
        registration_sha256=sha(REG),auditor_source_sha256=sha(__file__),target_requests=120,separate_warmups=120,unique_qa=60,runs=runs,
        answerable_f1_delta=runs[1]['answerable_f1']-runs[0]['answerable_f1'],output_hash_changes=sum(a[k]['output_hash']!=b[k]['output_hash'] for k in a),
        per_question_score_changes=dict(improved=sum(bq[k]['score']>aq[k]['score'] for k in aq),decreased=sum(bq[k]['score']<aq[k]['score'] for k in aq),equal=sum(bq[k]['score']==aq[k]['score'] for k in aq)),
        scope='Two actual profiled development arms/60already-exposed answerableQA only; no category5 test. Native constructor/code identities, whole warm/target ledgers and source accounting reopened; official scores recomputed. Candidate has zero inflation in eligible sampled states versus a positive reference control. Not complete incidence, production-liveness, STORE/DMA bytes, quality equivalence, latency gain, complete four-full comparison or competitive contribution.')
    out.write_text(json.dumps(result,indent=2)+'\n');print('Two-arm native invariant check:',[(p['mode'],p['probe']['eligible_sampled_prefetch_states'],p['probe']['distinct_inflated_ids']) for p in runs],flush=True)


if __name__=='__main__':main()
