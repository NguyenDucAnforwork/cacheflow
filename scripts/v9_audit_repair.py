"""Reopen all six diagnostic ledgers/proofs; recompute official quality."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from v6_raw_archive import sha
from v6_main_resources import analyze
from v8_observe_lookup_watermark import inflated_snapshots
from v7_observe_full_liveness import parsed_lines
from v9_repair import BASE,REG,plan,verify,probe_audit


def read(path):return json.loads(Path(path).read_text())


def audit():
    out=BASE/'v9repair1_audit.json';assert not out.exists();r=read(REG);verify(r)
    terminal_path=BASE/'v9repair1_terminal.json';terminal=read(terminal_path)
    assert terminal['diagnostic_execution_complete'] is True and terminal['error'] is None and terminal['cleanup_errors']==[]
    assert terminal['registration_sha256']==sha(REG) and [o['run_id'] for o in terminal['outcomes']]==[s['run_id'] for s in plan()]
    engines=set();caches=set();runs=[];qualities={};requests={}
    for step,outcome in zip(plan(),terminal['outcomes']):
        rid=step['run_id'];ap=BASE/(rid+'.repair_audit.json');assert sha(ap)==outcome['audit_sha256'];a=read(ap)
        assert a['step']==step and a['registration_sha256']==sha(REG) and a['diagnostic_integrity_checked'] and not a['performance_valid']
        both=[]
        for warm in [True,False]:
            current=rid+'-warm' if warm else rid;raw=BASE/'raw';setup_path=BASE/(current+'.diagnostic_setup.json');setup=read(setup_path)
            metadata=read(BASE/(current+'.diagnostic_integrity.json'));identity_path=BASE/(current+'.native_identity.json');identity=read(identity_path)
            assert metadata['registration_sha256']==identity['registration_sha256']==setup['registration_sha256']==sha(REG)
            assert metadata['setup_sha256']==identity['setup_sha256']==sha(setup_path) and not metadata['performance_valid']
            for name,digest in metadata['raw_sha256'].items():assert sha(name)==digest,name
            expected_step=dict(step,run_id=current,trace='data/processed/v3/v5-dev4b3-qps4-s101.jsonl',requests=60,policy='fifo') if warm else step
            assert setup['step']==expected_step and setup['capture_source_sha256']==sha('scripts/v9_repair_capture.py')
            runtime=setup['runtime'];assert runtime['max_inflight']==64 and runtime['max_queue']==512 and runtime['max_bypasses']==8 and runtime['kv_capacity_tokens']==43664
            assert runtime['model_key']=='qwen3-4b' and runtime['cpu_l1_bytes']==48002236416 and runtime['max_num_seqs']==16 and runtime['max_num_batched_tokens']==8192
            assert runtime['profile'] is False and runtime['kv_events'] is False and runtime['residency_events'] is False and runtime['enforce_eager'] is False
            assert setup['gateway_before']['active']==setup['gateway_before']['queue']==0 and setup['gateway_before']['upstream_read_timeout_s']==600
            s=read(raw/(current+'.summary.json'));manifest=read(Path(expected_step['trace']).with_suffix('.manifest.json'))
            assert s['run_id']==current and s['requests']==expected_step['requests'] and s['trace_sha256']==manifest['trace_sha256']
            assert s['model_revision']=='1cfa9a7208912126459214e8b04321603b3df60c' and s['gpu_kv_bytes']==6442450944 and s['max_model_len']==32768 and s['output_tokens_budget']==96
            assert s['request_read_timeout_s']==s['request_pool_timeout_s']==600 and s['client_keepalive_connections']==0
            assert s['engine_pid']==setup['engine']['pid'] and s['lmcache_pid']==setup['lmcache']['pid']
            rows=parsed_lines((raw/(current+'.jsonl')).read_bytes());outputs=parsed_lines((raw/(current+'.outputs.jsonl')).read_bytes())
            by={row['request_id']:row for row in rows};texts={row['request_id']:row for row in outputs}
            assert len(by)==len(rows)==len(outputs)==len(texts)==s['requests'] and by.keys()==texts.keys()
            import hashlib
            if not warm and step['requests']==1986:
                pre=read(BASE/'v6full1_input_preflight.json');fp=Path(pre['main_fingerprints_path']);assert sha(fp)==pre['main_fingerprints_sha256']
                templates={row['request_id']:row for row in read(fp)['requests']}
            else:
                templates={row['request_id']:dict(row,prompt_sha256=hashlib.sha256(row['prompt'].encode()).hexdigest()) for row in parsed_lines(Path(expected_step['trace']).read_bytes())}
            assert by.keys()==templates.keys()
            for request_id,row in by.items():
                assert row['run_id']==current and texts[request_id]['run_id']==current and row['status']==texts[request_id]['status']
                assert hashlib.sha256(texts[request_id]['output'].encode()).hexdigest()==row['output_hash']
                assert row['trace_sha256']==s['trace_sha256'] and row['engine_request_id']==current+'-'+request_id
                for key in ['sample_id','qa_index','input_tokens','prompt_sha256']:assert row[key]==templates[request_id][key],key
                if row['status']=='ok':assert row['server_prompt_tokens']==row['input_tokens'] and 0<row['output_tokens']<=96
            assert sum(row['status']=='ok' for row in rows)==s['successes'] and s['errors']==len(rows)-s['successes']
            gate=parsed_lines((raw/(current+'.gateway.jsonl')).read_bytes());gate_by={row['request_id']:row for row in gate}
            assert len(gate)==len(gate_by) and gate_by.keys()<=by.keys()
            assert {row['request_id'] for row in rows if row['status']=='ok'}<=gate_by.keys()
            if s['errors']==0:assert gate_by.keys()==by.keys() and all(row['status']=='ok' and row['input_tokens']==by[rid]['input_tokens'] for rid,row in gate_by.items())
            before=identity['before'];after=identity['after'];assert before['mode']==after['mode']==step['mode']
            assert before['engine_pid']==after['engine_pid']==s['engine_pid'] and before['engine_birth']==after['engine_birth']==setup['engine']['birth']
            assert before['checked_monotonic_ns']<min(row['client_send_ns'] for row in rows)
            assert {row['connector_role'] for row in before['constructor_records']}=={'KVConnectorRole.SCHEDULER','KVConnectorRole.WORKER'}
            for proof in before['constructor_records']:
                for key,value in r['native_method_expected'][step['mode']].items():assert proof[key]==value,key
                assert proof['monotonic_ns']<before['checked_monotonic_ns']
            for name,digest in before['proof_sha256'].items():assert sha(name)==digest,name
            if s['errors']==0:
                assert after['end_identity_verified'] and after['checked_monotonic_ns']>max(row['complete_ns'] for row in rows)
                assert after['proof_sha256']==before['proof_sha256'] and after['constructor_records']==before['constructor_records']
            if warm:assert s['errors']==0
            else:
                assert a['result']==dict(metadata,native_identity_sha256=sha(identity_path))
                resource=analyze(parsed_lines((raw/(rid+'.metrics.jsonl')).read_bytes()));assert resource==a['resources'];requests[rid]=by
                if s['errors']==0:
                    qp=BASE/(rid+'.quality.json');assert a['quality_sha256']==sha(qp)
                    with tempfile.TemporaryDirectory(prefix='cacheflow-v9-quality-') as folder:
                        recomputed=Path(folder)/'quality.json'
                        subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir',str(raw),'--run-ids',rid,'--output',str(recomputed)],check=True,stdout=subprocess.DEVNULL)
                        assert read(recomputed)==read(qp),'Official quality recomputation differs'
                    q=read(qp)['runs'][0];assert len(q['per_request'])==s['requests'];qualities[rid]=q
                    c=resource['strict_counter_deltas']['vllm'];assert c['vllm:prompt_tokens_total']==sum(row['input_tokens'] for row in rows)
                    assert c['vllm:prompt_tokens_cached_total']+c['vllm:request_prefill_kv_computed_tokens_sum']==c['vllm:prompt_tokens_total']
                else:assert a['quality_sha256'] is None
            both.append((setup,s))
        assert both[0][0]['engine']==both[1][0]['engine'] and both[0][0]['lmcache']==both[1][0]['lmcache']
        engine=(both[1][0]['engine']['pid'],both[1][0]['engine']['birth']);cache=(both[1][0]['lmcache']['pid'],both[1][0]['lmcache']['birth'])
        assert engine not in engines and cache not in caches;engines.add(engine);caches.add(cache)
        host=read(BASE/(rid+'.host_status.json'));assert host['storage_manager']['l1_manager']['memory_total_bytes']==48049946624
        if step['probe']:
            probe=probe_audit(step,r);assert probe==a['probe'] and probe['eligible_sampled_prefetch_states']>0
            assert (probe['distinct_inflated_ids']==0) if step['mode']=='idempotent' else (probe['distinct_inflated_ids']>0)
        else:assert a['probe'] is None and not list((BASE/'raw').glob(step['probe_label']+'.*.jsonl'))
        runs.append(dict(run_id=rid,mode=step['mode'],stage=step['stage'],requests=a['result']['requests'],errors=a['result']['errors'],audit_sha256=sha(ap),
            quality_sha256=a['quality_sha256'],probe=a['probe']))
    pairs=[]
    for seed in [901,902]:
        ar=f'v9repair1-full-reference-s{seed}';br=f'v9repair1-full-idempotent-s{seed}';aa=next(a for a in runs if a['run_id']==ar);bb=next(a for a in runs if a['run_id']==br)
        x=requests[ar];y=requests[br];assert x.keys()==y.keys() and len(x)==1986
        assert all(x[k]['prompt_sha256']==y[k]['prompt_sha256'] and x[k]['input_tokens']==y[k]['input_tokens'] for k in x)
        pair=dict(seed=seed,reference=ar,idempotent=br,reference_errors=aa['errors'],idempotent_errors=bb['errors'],quality_and_work_comparison=None)
        if aa['errors']==bb['errors']==0:
            aq=qualities[ar];bq=qualities[br];a=read(BASE/(ar+'.repair_audit.json'));b=read(BASE/(br+'.repair_audit.json'))
            assert aq['answerable_n']==bq['answerable_n']==1540 and aq['by_category']['5']['n']==bq['by_category']['5']['n']==446
            pair['quality_and_work_comparison']=dict(answerable_f1_delta=bq['answerable_f1']-aq['answerable_f1'],
                category5_mean_delta=bq['by_category']['5']['mean']-aq['by_category']['5']['mean'],output_hash_changes=sum(x[k]['output_hash']!=y[k]['output_hash'] for k in x),
                reference_new_prefill=a['resources']['strict_counter_deltas']['vllm']['vllm:request_prefill_kv_computed_tokens_sum'],
                idempotent_new_prefill=b['resources']['strict_counter_deltas']['vllm']['vllm:request_prefill_kv_computed_tokens_sum'])
        pairs.append(pair)
    result=dict(complete_repair_diagnostic_audit=True,performance_valid=False,research_complete=False,registration_sha256=sha(REG),terminal_sha256=sha(terminal_path),
        target_requests=sum(s['requests'] for s in plan()),separate_warmups=360,distinct_engines=len(engines),distinct_cpu_caches=len(caches),runs=runs,full_pairs=pairs,
        scope='All six diagnostic artifacts reopened, effective native code/fresh processes/whole ledgers/probe coverage/source work/official quality recomputed. No latency speedup, fullprimarybenchmark, production-liveness, quality equivalence or competitive contribution claim. Failed arms remain whole outcomes.')
    out.write_text(json.dumps(result,indent=2)+'\n');print('All6native repair diagnostic arms independently audited; no primary performance claim',flush=True)


if __name__=='__main__':audit()
