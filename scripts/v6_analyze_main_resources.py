"""Audit retained resource samples for all 24 completed main development arms."""
import json
import math
import statistics
from pathlib import Path
from v6_raw_archive import sha
from v6_main_resources import analyze
from v3_analyze_runs import load


def main():
    base=Path('results/v3');ap=base/'v6dev1_main_audit.json';audit=json.loads(ap.read_text())
    assert len(audit['runs'])==24 and audit['requests']==1440 and audit['errors']==0
    rp=base/'v6dev1_main_registration.json';reg=json.loads(rp.read_text())
    assert sha(rp)==audit['registration_sha256']
    for name,digest in reg['source_sha256'].items():assert sha(name)==digest,name
    sources=['src/cacheflow/collect_metrics.py','src/cacheflow/v2_metrics.py']
    runs=[]
    for r in audit['runs']:
        rid=r['run_id'];run=load(rid);sp=base/(rid+'.setup.json');setup=json.loads(sp.read_text())
        assert sha(base/'raw'/(rid+'.jsonl'))==r['fairness']['request_file_sha256']
        for name in sources:assert setup['source_files_sha256'][name]==sha(name),(rid,name)
        assert all(setup['source_files_sha256'][n]==h for n,h in reg['source_sha256'].items())
        assert run['summary']['engine_pid']==r['engine_pid'] and run['summary']['lmcache_pid']==r['lmcache_pid']
        assert setup['gateway_after'].get('decision_stats')==r['decision_stats']
        mp=base/'raw'/(rid+'.metrics.jsonl');samples=[json.loads(l) for l in mp.read_text().splitlines()]
        resource=analyze(samples);c=resource['strict_counter_deltas']['vllm'];expected=run['metrics']['counter_deltas']['vllm']
        weights=[(b['timestamp_ns']-a['timestamp_ns'])/1e9 for a,b in zip(samples,samples[1:])]
        environment={}
        for key in ['sm_clock_mhz','temperature_c']:
            values=[s.get('gpu',{}).get(key) for s in samples[:-1]]
            environment[key]=sum(v*w for v,w in zip(values,weights))/sum(weights) if all(v is not None and math.isfinite(v) for v in values) else None
        for key in ['vllm:prompt_tokens_total','vllm:prompt_tokens_cached_total','vllm:request_prefill_kv_computed_tokens_sum',
                    'vllm:prompt_tokens_source_external_kv_transfer_total','vllm:num_preemptions_total']:
            assert c[key] is not None and c[key]==expected[key],(rid,key)
        assert c['vllm:prompt_tokens_total']==sum(row['input_tokens'] for row in run['requests'].values())
        assert c['vllm:request_prefill_kv_computed_tokens_sum']==r['computed_tokens']
        assert c['vllm:prompt_tokens_source_external_kv_transfer_total']==r['consumed_cpu_tokens']
        assert resource['first_sample_ns']<min(row['scheduled_arrival_ns'] for row in run['requests'].values())
        assert resource['last_sample_ns']>max(row['complete_ns'] for row in run['requests'].values())
        cpu_evidence={}
        for source in ['vllm','lmcache']:
            counts=[s.get('process',{}).get(source,{}).get('processes') for s in samples]
            values=[s.get('process',{}).get(source,{}).get('cpu_seconds') for s in samples]
            cpu_evidence[source]=dict(observed_process_counts=sorted({c for c in counts if c is not None}),
                complete_cpu_samples=all(v is not None for v in values),
                monotonic_cpu_samples=all(a is not None and b is not None and b>=a for a,b in zip(values,values[1:])),
                identity_scope='Counts and aggregate CPU samples do not prove stable identities of every descendant.')
        power=resource['gpu_time_weighted_power_w']
        runs.append(dict(run_id=rid,arm=r['arm'],seed=r['seed'],requests=r['requests'],resource=resource,
            sampled_board_energy_estimate_j=power*resource['sample_window_s'] if power is not None else None,
            sampled_gpu_environment=environment,
            gateway_scheduler_decision_stats=r['decision_stats'],
            request_duration_s=run['summary']['duration_s'],process_sample_evidence=cpu_evidence,
            metrics_file_sha256=sha(mp),setup_sha256=sha(sp)))
    assert sum(r['requests'] for r in runs)==1440
    metrics={'sample_window_s':lambda r:r['resource']['sample_window_s'],
        'gpu_util_pct':lambda r:r['resource']['gpu_time_weighted_util_pct'],
        'gpu_board_power_w':lambda r:r['resource']['gpu_time_weighted_power_w'],
        'gpu_board_energy_estimate_j':lambda r:r['sampled_board_energy_estimate_j'],
        'gpu_sm_clock_mhz':lambda r:r['sampled_gpu_environment']['sm_clock_mhz'],
        'gpu_temperature_c':lambda r:r['sampled_gpu_environment']['temperature_c'],
        'gateway_decision_cpu_ms':lambda r:(r['gateway_scheduler_decision_stats'] or {}).get('cpu_ms'),
        'gateway_decision_run_max_ms':lambda r:(r['gateway_scheduler_decision_stats'] or {}).get('max_ms'),
        'vram_peak_mib':lambda r:r['resource']['vram_peak_mib'],
        'vllm_sampled_cpu_s':lambda r:r['resource']['process']['vllm']['sampled_cpu_seconds'],
        'lmcache_sampled_cpu_s':lambda r:r['resource']['process']['lmcache']['sampled_cpu_seconds'],
        'vllm_summed_rss_peak_bytes':lambda r:r['resource']['process']['vllm']['summed_rss_peak_bytes'],
        'lmcache_summed_rss_peak_bytes':lambda r:r['resource']['process']['lmcache']['summed_rss_peak_bytes']}
    aggregate=[]
    for arm in dict.fromkeys(r['arm'] for r in runs):
        rr=[r for r in runs if r['arm']==arm];assert len(rr)==3 and {r['seed'] for r in rr}=={101,102,103}
        values={k:[f(r) for r in rr] for k,f in metrics.items()}
        aggregate.append(dict(arm=arm,seeds=[r['seed'] for r in rr],metrics={k:dict(per_run=v,observed_runs=sum(x is not None for x in v),
            mean=statistics.mean(v) if all(x is not None for x in v) else None) for k,v in values.items()}))
    analysis=['scripts/v6_analyze_main_resources.py','scripts/v6_main_resources.py','scripts/v3_analyze_runs.py',*sources]
    result=dict(complete_resource_supplement=True,source_main_audit_sha256=sha(ap),registration_sha256=sha(rp),
        requests=1440,errors=0,runs=runs,aggregate=aggregate,analysis_source_sha256={n:sha(n) for n in analysis},
        scope='All24audited main development arms,60exposed QA repeated3schedules; no new serving. Left-endpoint1Hz sampled-window GPU utilization/power/board-energy estimates include pre/post-request margins. Not kernel busy-time, exact energy, host energy, physical system memory or throughput capacity. CPU is sampled process-tree endpoint delta; counts cannot prove every descendant identity stable. Gateway decision CPU is separate instrumented thread CPU around chooser calls, including cache hits; excludes tokenizer, HTTP and other gateway work. Missing decision counters are not zero. Summed RSS double-counts shared pages and omits gateway/client. Missing runs are not averaged away. Not the full benchmark or cross-engine comparison.')
    output=base/'v6dev1_main_resources.json';output.write_text(json.dumps(result,indent=2)+'\n')
    for r in aggregate:print(r['arm'],{k:round(v['mean'],3) if v['mean'] is not None else None for k,v in r['metrics'].items()})


if __name__=='__main__':main()
