"""Audit all24 fresh-process main arms; incomplete/failed runs get no quantiles."""
import hashlib
import json
import statistics
import subprocess
import sys
from pathlib import Path
import yaml
from v6_main_matrix import build_plan
from v5_verify import verify
from v3_analyze_runs import load
from v5_analyze_decode import analyze as decode
from v5_analyze_histograms import analyze as native_histogram
from v5_run_intervals import paired_log_interval
from v6_analyze_fairness import analyze as fairness


def main():
    parent,seal=verify();base=Path('results/v3');raw=base/'raw';path=base/'v6dev1_main_registration.json';reg=json.loads(path.read_text())
    assert reg['actions']==build_plan() and len(reg['actions'])==24
    for name,digest in reg['source_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    missing=[];failed=[]
    for step in reg['actions']:
        for rid in [step['run_id']+'-warm',step['run_id']]:
            p=raw/f'{rid}.summary.json'
            if not p.exists():missing.append(rid)
            else:
                s=json.loads(p.read_text())
                if s['errors'] or s['successes']!=s['requests'] or (base/f'{rid}.invalid').exists():failed.append(rid)
    if missing or failed:
        (base/'v6dev1_main_incomplete.json').write_text(json.dumps(dict(complete=False,missing=missing,failed=failed,
            scope='Incomplete/failed matrix; no complete-success percentile or quality-equivalence claim'),indent=2)+'\n')
        raise RuntimeError('Matrix incomplete/failed; inspect retained outcomes rather than retrying')
    assert hashlib.sha256(Path('/etc/supervisor/conf.d/cacheflow_v2_gateway.conf').read_bytes()).hexdigest()==reg['original_supervisor_sha256'], 'Gateway supervisor config was not restored after terminal matrix'
    rows=[];loaded={};secondary=[];host_sizes=set()
    for step in reg['actions']:
        rid=step['run_id'];run=load(rid);s=run['summary'];loaded[rid]=run
        setup=json.loads((base/f'{rid}.setup.json').read_text());entry=json.loads((base/f'{rid}.v6_entrypoint.json').read_text())
        cfg=yaml.safe_load(setup['gateway_config']);runtime=setup['runtime'];m=json.loads(Path(step['trace']).with_suffix('.manifest.json').read_text())
        warm=json.loads((raw/f'{rid}-warm.summary.json').read_text());assert warm['requests']==warm['successes']==60 and warm['engine_pid']==s['engine_pid'] and warm['lmcache_pid']==s['lmcache_pid']
        assert s['requests']==s['successes']==m['requests']==60 and not s['errors']
        assert s['policy']==cfg['scheduler']['policy']==setup['gateway_before']['policy']==step['policy']
        assert cfg['scheduler']['max_inflight']==runtime['max_inflight']==step['cap'] and cfg['scheduler']['max_queue']==64
        assert cfg['residency']['max_bypasses']==8 and cfg['upstream_keepalive_connections']==0
        assert s['request_read_timeout_s']==s['request_pool_timeout_s']==cfg['http_read_timeout_s']==180 and s['client_keepalive_connections']==0
        assert s['trace_sha256']==m['trace_sha256'] and s['prompt_version']=='locomo-qwen-concise-v5'
        assert s['model_revision']==parent['model_revision'] and s['source_sha256']==parent['source_data_sha256'] and s['output_tokens_budget']==96
        assert setup['gateway_before']['completed_history_requests']==0 and setup['gateway_before']['prepare_mode']=='thread'
        assert runtime['residency_events'] and runtime['cpu_l1_bytes']==16000745472 and runtime['max_num_seqs']==16
        assert not any(runtime.get(k) for k in ['profile','kv_events','batch_invariant','enforce_eager'])
        observer=setup['gateway_after']['residency'];assert observer['known'] and observer['hash_contract_verified'] and observer['gaps']==0
        assert 'cacheflow.v6_gateway:create_app' in entry['gateway_argv'] and entry['source_sha256']==reg['source_sha256'] and not entry['native_probe'] and not entry['upstream_profile']
        for name,digest in (parent['source_sha256']|reg['source_sha256']).items():assert setup['source_files_sha256'][name]==digest,(rid,name)
        host=json.loads((base/f'{rid}.host_status.json').read_text())['storage_manager']['l1_manager']['memory_total_bytes'];host_sizes.add(host)
        assert host==16039018496
        secondary.append(decode(rid));c=run['metrics']['counter_deltas']['vllm']
        rows.append(dict(**step,requests=60,engine_pid=s['engine_pid'],lmcache_pid=s['lmcache_pid'],
            **{k:s['arrival_ttft_'+k] for k in ['p50_ms','p95_ms','p99_ms']},
            computed_tokens=c['vllm:request_prefill_kv_computed_tokens_sum'],consumed_cpu_tokens=c['vllm:prompt_tokens_source_external_kv_transfer_total'],
            gpu_source_tokens=c['vllm:prompt_tokens_source_local_cache_hit_total'],preemptions=c['vllm:num_preemptions_total'],
            decision_stats=setup['gateway_after']['decision_stats'],fairness=fairness(rid)))
    assert len({r['engine_pid'] for r in rows})==len({r['lmcache_pid'] for r in rows})==24 and len(host_sizes)==1
    quality_path=base/'v6dev1_main_quality.json'
    subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir',str(raw),'--run-ids',*[r['run_id'] for r in rows],'--output',str(quality_path)],check=True)
    quality={r['run_id']:r for r in json.loads(quality_path.read_text())['runs']}
    for r in rows:r.update(f1=quality[r['run_id']]['answerable_f1'],output_budget_hits=quality[r['run_id']]['output_budget_hits'])
    by={r['run_id']:r for r in rows};pairs=[];aggregates=[]
    arms=list(dict.fromkeys(r['arm'] for r in rows))
    for seed in [101,102,103]:
        b=f'v6dev1-main-packing_ready-s{seed}';bb=loaded[b]
        for arm in arms:
            if arm=='packing_ready':continue
            a=f'v6dev1-main-{arm}-s{seed}';aa=loaded[a]
            assert aa['summary']['trace_sha256']==bb['summary']['trace_sha256'] and aa['requests'].keys()==bb['requests'].keys()
            assert all(aa['requests'][k]['prompt_sha256']==bb['requests'][k]['prompt_sha256'] for k in aa['requests'])
            pairs.append(dict(a=a,b=b,process_scope='Distinct fresh serving processes; matched semantic configuration',
                **{k+'_delta_pct':100*(by[b][k]/by[a][k]-1) for k in ['p50_ms','p95_ms','p99_ms']},
                f1_delta=by[b]['f1']-by[a]['f1'],output_hash_mismatches=sum(aa['requests'][k]['output_hash']!=bb['requests'][k]['output_hash'] for k in aa['requests'])))
    for arm in arms:
        rr=[r for r in rows if r['arm']==arm];assert len(rr)==3
        def known_mean(key):
            values=[r[key] for r in rr]
            return statistics.mean(values) if all(v is not None for v in values) else None
        aggregates.append(dict(arm=arm,**{k:known_mean(k) for k in ['p50_ms','p95_ms','p99_ms','computed_tokens','consumed_cpu_tokens','gpu_source_tokens','preemptions','f1']},output_budget_hits=sum(r['output_budget_hits'] for r in rr)))
    intervals=[]
    for arm in arms:
        if arm=='packing_ready':continue
        intervals.append(dict(baseline_arm=arm,candidate_arm='packing_ready',metrics={key:paired_log_interval(
            [by[f'v6dev1-main-{arm}-s{seed}'][key] for seed in [101,102,103]],
            [by[f'v6dev1-main-packing_ready-s{seed}'][key] for seed in [101,102,103]]) for key in ['p50_ms','p95_ms','p99_ms']}))
    result=dict(scope='Complete24-arm development matrix:60unique previously exposedQA,3arrival schedules with fresh process per arm. Means of run quantiles. No semantic-population or quality-equivalence inference; source tokens are not DMA bytes. Effective main host heaps equal within stack; no actual cross-engine parity claim.',
        registration_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),requests=1440,errors=0,separate_warmup_requests=1440,
        actual_main_host_heap_bytes=next(iter(host_sizes)),runs=rows,pairs=pairs,aggregate=aggregates,secondary=secondary)
    result.update(exploratory_run_intervals=intervals,interval_scope='Paired log-ratio t(df2) descriptors on3arrival-seed/fresh-process units, fixed QA/model/host. Independence/normality unverified at n3; not population significance or quality equivalence.')
    native=[];missing_native=[]
    for row in rows:
        snapshot=base/f"{row['run_id']}.itl_histogram.json"
        if snapshot.exists():
            try:native.append(native_histogram(snapshot))
            except (AssertionError,ValueError,KeyError) as exc:
                native.append(dict(run_id=row['run_id'],coverage_valid=False,coverage_failures=['Supplemental histogram validation failed: '+repr(exc)],native_itl_mean_ms=None,quantile_bounds=None))
        else:missing_native.append(row['run_id'])
    result.update(native_itl=native,missing_native_itl_snapshots=missing_native,
        native_itl_scope='Supplemental passive native engine-update histograms; incomplete coverage stays null and is separate from the complete primary request audit. Bucket bounds are not exact client token quantiles.')
    (base/'v6dev1_main_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    subprocess.run([sys.executable,'scripts/v6_normalize_registry.py'],check=True)
    for r in aggregates:print(r)


if __name__=='__main__':main()
