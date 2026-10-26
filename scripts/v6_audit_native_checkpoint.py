"""Audit one completed native development block without claiming the60-arm stage."""
import json
import argparse
from pathlib import Path
from v5_verify import verify
from v6_freeze_full import sha
from v4_audit_sglang_runs import audit as integrity
from v6_native_metrics import summarize
from v6_analyze_fairness import analyze as fairness
from v5_analyze_histograms import analyze as histogram
from v5_analyze_decode import analyze as decode
from v2_quality_audit import EVALUATOR_SHA256


def read(path):return json.loads(Path(path).read_text())


def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,choices=[101,102,103],default=101);args=p.parse_args();seed=args.seed
    parent,seal=verify();base=Path('results/v3/sglang');raw=Path('results/v3/raw/sglang');rp=base/'v6native1_registration.json';reg=read(rp)
    for name,digest in reg['source_sha256'].items():assert sha(name)==digest,name
    block=next(b for b in reg['blocks'] if b['regime']=='primary' and b['seed']==seed);assert len(block['actions'])==5
    qualitypath=base/f'v6native1_primary_s{seed}_checkpoint_quality.json';quality=read(qualitypath)
    assert quality['evaluator_sha256']==EVALUATOR_SHA256 and quality['source_sha256']==parent['source_data_sha256']
    qs={r['run_id']:r for r in quality['runs']};warm=read(raw/(block['warmup']['run_id']+'.summary.json'))
    assert warm['requests']==warm['successes']==60 and warm['errors']==0
    results=[];maps={}
    for step in block['actions']:
        rid=step['run_id'];verified=integrity(rid);s=read(raw/(rid+'.summary.json'));setup=read(base/(rid+'.setup.json'));runtime=setup['runtime'];sc=setup['server_config']
        assert verified['requests']==60 and not verified['errors'] and s['engine_pid']==warm['engine_pid']
        assert s['request_read_timeout_s']==s['request_pool_timeout_s']==180 and s['client_keepalive_connections']==0
        assert s['model_revision']==parent['model_revision'] and s['source_sha256']==parent['source_data_sha256'] and s['output_tokens_budget']==96
        assert s['prompt_version']=='locomo-qwen-concise-v5' and s['trace_sha256']==read(Path(step['trace']).with_suffix('.manifest.json'))['trace_sha256']
        assert runtime['schedule_policy']=='lpm' and runtime['gpu_kv_gib']==6 and runtime['host_kv_gib']==16
        assert runtime['same_batch_guard'] and not runtime['profile_transfers'] and runtime['max_running_requests']==16
        assert sc['max_total_tokens']==43680 and sc['hicache_size']==16 and sc['max_running_requests']==16
        assert sc['hicache_io_backend']=='direct' and sc['attention_backend']=='flashinfer' and sc['model_path'].endswith(parent['model_revision'])
        assert setup['gateway_policy']==step['policy'] and setup['package_versions']==reg['package_versions'] and setup['upstream_source_sha256']==reg['upstream_source_sha256']
        snapshots={}
        for key in ['frontend_source_sha256','native_overlay_source_sha256','gateway_source_sha256','v6_source_sha256']:snapshots.update(setup.get(key,{}))
        expected=parent['source_sha256']|reg['source_sha256']
        required={'scripts/v6_sglang_bench.py','scripts/v6_native_metrics.py','src/cacheflow/v6_replay.py','scripts/sglang_profile_hooks/sitecustomize.py','src/cacheflow/v4_sglang_delayhit.py'}
        if step['policy']:
            assert 'cacheflow.v6_gateway:create_app' in setup['gateway_runtime_entrypoint']['argv']
            required|={'src/cacheflow/v6_gateway.py','src/cacheflow/v6_ready_scheduler.py','scripts/v6_runtime.py','scripts/v6_serve_gateway.sh'}
        for name in required:assert snapshots[name]==expected[name],name
        for name,digest in snapshots.items():
            if name in expected:assert digest==expected[name],name
        requests=[json.loads(l) for l in (raw/(rid+'.jsonl')).read_text().splitlines()];maps[rid]={r['request_id']:r for r in requests}
        snapshot=read(base/(rid+'.itl_histogram.json'));assert snapshot['request_file_sha256']==sha(raw/(rid+'.jsonl'))
        check=summarize(rid,snapshot['before'],snapshot['after'],requests,s,'sglang')
        assert check['coverage_valid']==snapshot['coverage_valid'] and check['coverage_failures']==snapshot['coverage_failures']
        m=read(base/(rid+'.metrics_summary.json'));counter='sglang:load_back_tokens_total';q=qs[rid]
        results.append(dict(**step,engine_pid=s['engine_pid'],**{k:s['arrival_ttft_'+k] for k in ['p50_ms','p95_ms','p99_ms']},
            computed_tokens=m['counter_deltas']['sglang:uncached_prompt_tokens_histogram_sum'],host_promoted_tokens=m['counter_deltas'].get(counter),
            host_promotion_endpoints=dict(first=m['first_counter_endpoints'].get(counter),last=m['last_counter_endpoints'].get(counter)),
            f1=q['answerable_f1'],output_budget_hits=q['output_budget_hits'],native_itl=histogram(base/(rid+'.itl_histogram.json')),
            secondary=decode(rid),fairness=fairness(rid),setup_sha256=sha(base/(rid+'.setup.json')),request_file_sha256=sha(raw/(rid+'.jsonl'))))
    assert len({r['engine_pid'] for r in results})==1
    by={r['arm']:r for r in results};pairs=[]
    for candidate,baseline in [('union64','native'),('packing_ready','native'),('packing_ready','union64'),('ready_fifo','native')]:
        a=by[baseline];b=by[candidate];aa=maps[a['run_id']];bb=maps[b['run_id']];assert aa.keys()==bb.keys()
        assert all(aa[k]['prompt_sha256']==bb[k]['prompt_sha256'] for k in aa)
        pairs.append(dict(baseline=baseline,candidate=candidate,**{k+'_delta_pct':100*(b[k]/a[k]-1) for k in ['p50_ms','p95_ms','p99_ms','computed_tokens']},
            f1_delta=b['f1']-a['f1'],output_hash_mismatches=sum(aa[k]['output_hash']!=bb[k]['output_hash'] for k in aa)))
    result=dict(completed_block=True,overall_native_stage_complete=False,registration_sha256=sha(rp),quality_sha256=sha(qualitypath),
        requests=300,errors=0,separate_warmup_requests=60,runs=results,pairs=pairs,
        scope=f'Single primary seed{seed}development block, same native engine with flush/fresh gateway between5arms;60exposedQA. Not three-seed evidence, not the60-arm stage, not full1986QA, not quality equivalence or a causal transfer reduction claim. Missing host-promotion counter endpoints remain null, never zero-filled.')
    (base/f'v6native1_primary_s{seed}_checkpoint_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in pairs:print(p)


if __name__=='__main__':main()
