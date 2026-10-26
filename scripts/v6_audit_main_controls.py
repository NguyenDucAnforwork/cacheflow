"""Strict complete-stage main controls audit; no successful-only tables."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import yaml
from v5_verify import verify
from v6_main_controls import build_plan,CONFIG
from v3_analyze_runs import load
from v6_native_metrics import summarize
from v5_analyze_histograms import analyze as histogram
from v5_analyze_decode import analyze as decode
from v5_run_intervals import paired_log_interval
from v6_analyze_fairness import analyze as fairness


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parent,seal=verify();base=Path('results/v3');raw=base/'raw';regpath=base/'v6controls1_main_registration.json'
    reg=json.loads(regpath.read_text());assert reg['actions']==build_plan() and len(reg['actions'])==36
    for name,digest in reg['source_sha256'].items():assert sha(name)==digest,name
    assert sha(CONFIG)==reg['original_supervisor_sha256']
    assert sha('results/v3/sglang/v6native1_audit.json')==reg['native_audit_sha256']
    for name,digest in reg['trace_sha256'].items():assert sha(name)==digest,name
    missing=[];failed=[]
    for step in reg['actions']:
        for rid in [step['run_id']+'-warm',step['run_id']]:
            path=raw/(rid+'.summary.json')
            if not path.exists():missing.append(rid);continue
            s=json.loads(path.read_text())
            if s['errors'] or s['successes']!=s['requests'] or (base/(rid+'.invalid')).exists():failed.append(rid)
    if missing or failed:
        (base/'v6controls1_main_incomplete.json').write_text(json.dumps(dict(complete=False,missing=missing,failed=failed),indent=2)+'\n')
        raise RuntimeError('Controls incomplete/failed; no complete-success quantile table')
    results=[];loaded={};pids=set();lmcachepids=set()
    for step in reg['actions']:
        rid=step['run_id'];run=load(rid);s=run['summary'];loaded[rid]=run
        setup=json.loads((base/(rid+'.setup.json')).read_text());cfg=yaml.safe_load(setup['gateway_config']);runtime=setup['runtime']
        entry=json.loads((base/(rid+'.v6_entrypoint.json')).read_text());m=json.loads(Path(step['trace']).with_suffix('.manifest.json').read_text())
        warm=load(rid+'-warm')['summary']
        assert warm['requests']==warm['successes']==60 and not warm['errors']
        assert warm['engine_pid']==s['engine_pid'] and warm['lmcache_pid']==s['lmcache_pid']
        assert s['requests']==s['successes']==step['requests']==m['requests'] and not s['errors']
        assert s['trace_sha256']==m['trace_sha256'] and s['prompt_version']==m['prompt_version']=='locomo-qwen-concise-v5'
        assert m['renderer_sha256']==seal['source_sha256']['src/cacheflow/v5_prompt.py'] and m['abstention_style']=='official_consistent_system_and_user'
        assert s['model_revision']==parent['model_revision'] and s['source_sha256']==parent['source_data_sha256'] and s['output_tokens_budget']==96
        assert s['gpu_kv_bytes']==setup['gpu_kv_bytes']==step['budget']*2**30
        assert runtime['kv_capacity_tokens']==cfg['residency']['kv_capacity_tokens']==(43664 if step['budget']==6 else 72800)
        assert s['policy']==cfg['scheduler']['policy']==setup['gateway_before']['policy']==step['policy']
        assert cfg['scheduler']['max_inflight']==runtime['max_inflight']==step['cap']==64
        assert cfg['scheduler']['max_queue']==64 and cfg['residency']['max_bypasses']==8
        assert s['request_read_timeout_s']==s['request_pool_timeout_s']==cfg['http_read_timeout_s']==180
        assert s['client_keepalive_connections']==cfg['upstream_keepalive_connections']==0
        assert setup['gateway_before']['active']==setup['gateway_before']['queue']==setup['gateway_before']['completed_history_requests']==0
        assert not (setup['gateway_before'].get('decision_stats') or {}).get('calls',0)
        assert setup['gateway_before']['prepare_mode']=='thread' and cfg['prepare_in_thread']
        assert runtime['residency_events'] and runtime['cpu_l1_bytes']==16000745472 and runtime['max_num_seqs']==16
        assert not any(runtime.get(k) for k in ['profile','kv_events','batch_invariant','enforce_eager'])
        observer=setup['gateway_after']['residency'];assert observer['known'] and observer['hash_contract_verified'] and observer['gaps']==0
        assert 'cacheflow.v6_gateway:create_app' in entry['gateway_argv'] and entry['source_sha256']==reg['source_sha256']
        assert not entry['native_probe'] and not entry['upstream_profile']
        for name,digest in (parent['source_sha256']|reg['source_sha256']).items():assert setup['source_files_sha256'][name]==digest,(rid,name)
        host=json.loads((base/(rid+'.host_status.json')).read_text())['storage_manager']['l1_manager']['memory_total_bytes'];assert host==16039018496
        snapshotpath=base/(rid+'.itl_histogram.json');snapshot=json.loads(snapshotpath.read_text())
        assert snapshot['request_file_sha256']==sha(raw/(rid+'.jsonl'))
        verified=summarize(rid,snapshot['before'],snapshot['after'],list(run['requests'].values()),s,'vllm')
        assert verified['coverage_valid']==snapshot['coverage_valid'] and verified['coverage_failures']==snapshot['coverage_failures']
        pids.add(s['engine_pid']);lmcachepids.add(s['lmcache_pid']);c=run['metrics']['counter_deltas']['vllm']
        results.append(dict(**step,engine_pid=s['engine_pid'],lmcache_pid=s['lmcache_pid'],
            **{k:s['arrival_ttft_'+k] for k in ['p50_ms','p95_ms','p99_ms']},
            computed_tokens=c['vllm:request_prefill_kv_computed_tokens_sum'],consumed_cpu_tokens=c['vllm:prompt_tokens_source_external_kv_transfer_total'],
            preemptions=c['vllm:num_preemptions_total'],actual_host_heap_bytes=host,native_itl=histogram(snapshotpath),secondary=decode(rid),fairness=fairness(rid)))
    assert len(pids)==len(lmcachepids)==36
    qualitypath=base/'v6controls1_main_quality.json'
    subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir',str(raw),'--run-ids',*[r['run_id'] for r in results],'--output',str(qualitypath)],check=True)
    quality={r['run_id']:r for r in json.loads(qualitypath.read_text())['runs']};by={r['run_id']:r for r in results};pairs=[];intervals=[]
    for r in results:r.update(f1=quality[r['run_id']]['answerable_f1'],output_budget_hits=quality[r['run_id']]['output_budget_hits'])
    for regime in ['lowload','lowreuse','gpufit','abstention']:
        for candidate,baseline in [('union64','fifo64'),('packing_ready','fifo64'),('packing_ready','union64')]:
            aa=[];bb=[]
            for seed in [101,102,103]:
                a=f'v6controls1-main-{regime}-{baseline}-s{seed}';b=f'v6controls1-main-{regime}-{candidate}-s{seed}'
                ar=loaded[a]['requests'];br=loaded[b]['requests'];assert ar.keys()==br.keys()
                assert all(ar[k]['prompt_sha256']==br[k]['prompt_sha256'] for k in ar)
                fa,fb=by[a]['f1'],by[b]['f1'];aa.append(by[a]);bb.append(by[b])
                pairs.append(dict(a=a,b=b,regime=regime,seed=seed,baseline=baseline,candidate=candidate,
                    **{k+'_delta_pct':100*(by[b][k]/by[a][k]-1) for k in ['p50_ms','p95_ms','p99_ms']},
                    f1_delta=fb-fa if fa is not None and fb is not None else None,
                    output_hash_mismatches=sum(ar[k]['output_hash']!=br[k]['output_hash'] for k in ar)))
            intervals.append(dict(regime=regime,baseline=baseline,candidate=candidate,metrics={k:paired_log_interval([r[k] for r in aa],[r[k] for r in bb]) for k in ['p50_ms','p95_ms','p99_ms']}))
    result=dict(complete=True,registration_sha256=sha(regpath),scope=reg['scope'],requests=sum(r['requests'] for r in results),errors=0,
        separate_warmup_requests=2160,runs=results,pairs=pairs,exploratory_intervals=intervals,
        limitations='n3paired log-ratio t(df2) descriptors are not semantic population significance or quality equivalence. Missing native coverage stays null. Source tokens are not measured DMA bytes. Report each regime/seed including regressions.')
    (base/'v6controls1_main_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Main controls audited',result['requests'],'requests',flush=True)


if __name__=='__main__':main()
