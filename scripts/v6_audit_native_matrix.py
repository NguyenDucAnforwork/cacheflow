"""Independent all-run integrity, quality and native-streaming audit for V6."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import yaml
from v5_verify import verify
from v6_native_matrix import build_plan,BASE,CONFIG
from v6_native_metrics import summarize
from v5_analyze_histograms import analyze as histogram
from v5_analyze_decode import analyze as decode
from v6_analyze_fairness import analyze as fairness


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parent,seal=verify();regpath=BASE/'v6native1_registration.json';reg=json.loads(regpath.read_text())
    assert reg['blocks']==build_plan()
    for name,digest in reg['source_sha256'].items():assert sha(name)==digest,name
    for name,digest in reg['trace_sha256'].items():assert sha(name)==digest,name
    raw=Path('results/v3/raw/sglang');missing=[];failed=[]
    for block in reg['blocks']:
        for step in [block['warmup'],*block['actions']]:
            rid=step['run_id'];path=raw/(rid+'.summary.json')
            if not path.exists():missing.append(rid);continue
            summary=json.loads(path.read_text())
            if summary['errors'] or summary['successes']!=step['requests'] or (BASE/(rid+'.invalid')).exists():failed.append(rid)
    if missing or failed:
        (BASE/'v6native1_incomplete.json').write_text(json.dumps(dict(complete=False,missing=missing,failed=failed),indent=2)+'\n')
        raise RuntimeError('Native matrix incomplete/failed; no complete-success percentile table')
    assert sha(CONFIG)==reg['original_supervisor_sha256']
    results=[];allpids=[];requestmaps={}
    for block in reg['blocks']:
        blockpids=set()
        for step in [block['warmup'],*block['actions']]:
            rid=step['run_id'];warm=rid==block['warmup']['run_id'];setup=json.loads((BASE/(rid+'.setup.json')).read_text())
            s=json.loads((raw/(rid+'.summary.json')).read_text());m=json.loads(Path(step['trace']).with_suffix('.manifest.json').read_text())
            rows=[json.loads(l) for l in (raw/(rid+'.jsonl')).read_text().splitlines()];runtime=setup['runtime']
            assert len(rows)==s['requests']==s['successes']==step['requests']==m['requests'] and not s['errors']
            assert len({r['request_id'] for r in rows})==len(rows)
            assert all(r['status']=='ok' and r['server_prompt_tokens']==r['input_tokens'] for r in rows)
            assert s['trace_sha256']==m['trace_sha256']==reg['trace_sha256'][step['trace']]
            assert s['prompt_version']==m['prompt_version']=='locomo-qwen-concise-v5'
            assert m['renderer_sha256']==seal['source_sha256']['src/cacheflow/v5_prompt.py']
            assert m['abstention_style']=='official_consistent_system_and_user'
            assert s['model_revision']==parent['model_revision'] and s['source_sha256']==parent['source_data_sha256'] and s['output_tokens_budget']==96
            assert s['request_read_timeout_s']==s['request_pool_timeout_s']==180 and s['client_keepalive_connections']==0
            assert runtime['schedule_policy']==block['native_policy'] and runtime['gpu_kv_gib']==block['budget']
            assert runtime['host_kv_gib']==16 and runtime['same_batch_guard'] and not runtime['profile_transfers']
            assert runtime['graphs'] and runtime['max_running_requests']==16 and runtime['batch_tokens']==8192
            assert runtime['io_backend']=='direct' and runtime['attention_backend']=='flashinfer'
            assert runtime['inbatch_check_threshold']==runtime['inbatch_deprioritize_threshold']==32
            assert setup['reset_status']==200 and setup['warmup']==warm
            assert setup['upstream_source_sha256']==reg['upstream_source_sha256']
            assert setup['package_versions']==reg['package_versions']
            snapshots={}
            for key in ['frontend_source_sha256','native_overlay_source_sha256','gateway_source_sha256','v6_source_sha256']:snapshots.update(setup.get(key,{}))
            required={'scripts/v6_sglang_bench.py','scripts/v6_native_metrics.py','src/cacheflow/v6_replay.py',
                'scripts/sglang_profile_hooks/sitecustomize.py','src/cacheflow/v4_sglang_delayhit.py'}
            if step.get('policy'):required|={'src/cacheflow/v6_gateway.py','src/cacheflow/v6_ready_scheduler.py','scripts/v6_runtime.py','scripts/v6_serve_gateway.sh'}
            for name in required:assert snapshots[name]==reg['source_sha256'][name],(rid,name)
            for name,digest in snapshots.items():
                if name in parent['source_sha256']:assert digest==parent['source_sha256'][name]
            if step.get('policy'):
                cfg=yaml.safe_load(setup['gateway_config']);before=setup['gateway_before'];after=setup['gateway_after']
                assert cfg['scheduler']['policy']==before['policy']==s['policy']==step['policy']
                assert cfg['scheduler']['max_inflight']==cfg['scheduler']['max_queue']==64
                assert cfg['residency']['max_bypasses']==8
                assert cfg['residency']['kv_capacity_tokens']==(43664 if block['budget']==6 else 72800)
                assert not cfg['residency']['enabled'] and cfg['upstream']=='http://127.0.0.1:8300'
                assert cfg['http_read_timeout_s']==before['upstream_read_timeout_s']==180
                assert cfg['upstream_keepalive_connections']==0 and cfg['prepare_in_thread'] and before['prepare_mode']=='thread'
                assert before['active']==before['queue']==before['completed_history_requests']==0
                assert not (before.get('decision_stats') or {}).get('calls',0)
                assert after['active']==after['queue']==0
                assert 'cacheflow.v6_gateway:create_app' in setup['gateway_runtime_entrypoint']['argv']
            else:assert setup['gateway_policy'] is None and setup['gateway_config'] is None
            counters=json.loads((BASE/(rid+'.metrics_summary.json')).read_text())['counter_deltas']
            assert counters['sglang:prompt_tokens_total']==sum(r['input_tokens'] for r in rows)
            if not warm:assert counters['sglang:cached_tokens_total']+counters['sglang:uncached_prompt_tokens_histogram_sum']==sum(r['input_tokens'] for r in rows)
            blockpids.add(s['engine_pid'])
            if warm:continue
            nativepath=BASE/(rid+'.itl_histogram.json');native=json.loads(nativepath.read_text())
            assert native['request_file_sha256']==sha(raw/(rid+'.jsonl'))
            verified=summarize(rid,native['before'],native['after'],rows,s,'sglang')
            assert verified['coverage_valid']==native['coverage_valid'] and verified['coverage_failures']==native['coverage_failures']
            requestmaps[rid]={r['request_id']:r for r in rows}
            results.append(dict(**step,regime=block['regime'],seed=block['seed'],engine_pid=s['engine_pid'],
                **{k:s[k] for k in ['arrival_ttft_p50_ms','arrival_ttft_p95_ms','arrival_ttft_p99_ms']},
                computed_tokens=counters.get('sglang:uncached_prompt_tokens_histogram_sum'),
                host_promoted_tokens=counters.get('sglang:load_back_tokens_total'),native_itl=histogram(nativepath),secondary=decode(rid),fairness=fairness(rid)))
        assert len(blockpids)==1;allpids.extend(blockpids)
    assert len(allpids)==len(set(allpids))==18 and len(results)==45
    qualitypath=BASE/'v6native1_quality.json'
    subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir',str(raw),'--run-ids',*[r['run_id'] for r in results],'--output',str(qualitypath)],check=True)
    quality={r['run_id']:r for r in json.loads(qualitypath.read_text())['runs']}
    by={r['run_id']:r for r in results};pairs=[]
    for r in results:r.update(f1=quality[r['run_id']]['answerable_f1'],output_budget_hits=quality[r['run_id']]['output_budget_hits'])
    for block in reg['blocks']:
        candidate=next(s['run_id'] for s in block['actions'] if s['arm']=='packing_ready')
        for step in block['actions']:
            a=step['run_id']
            if a==candidate:continue
            aa=requestmaps[a];bb=requestmaps[candidate];assert aa.keys()==bb.keys()
            assert all(aa[k]['prompt_sha256']==bb[k]['prompt_sha256'] for k in aa)
            fa,fb=by[a]['f1'],by[candidate]['f1']
            pairs.append(dict(a=a,b=candidate,regime=block['regime'],seed=block['seed'],
                p95_delta_pct=100*(by[candidate]['arrival_ttft_p95_ms']/by[a]['arrival_ttft_p95_ms']-1),
                f1_delta=fb-fa if fa is not None and fb is not None else None,
                output_hash_mismatches=sum(aa[k]['output_hash']!=bb[k]['output_hash'] for k in aa)))
    result=dict(complete=True,registration_sha256=sha(regpath),scope=reg['scope'],requests=sum(r['requests'] for r in results),
        errors=0,separate_warmup_requests=1080,runs=results,pairs=pairs)
    (BASE/'v6native1_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Audited native matrix',result['requests'],'requests',flush=True)


if __name__=='__main__':main()
