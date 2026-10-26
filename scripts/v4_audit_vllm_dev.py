"""Require all18 clean V4 main-stack runs and compare fixed-policy dev arms."""
import json
import statistics
from pathlib import Path
from v3_analyze_runs import load,compare
from v3_audit_admission import audit

arms=['fifo16','fifo64','lpm_real16','bundle_wave16','dhas16','packing_reuse64']
rows=[];pairs=[];reference_setup=None
relevant=['src/cacheflow/gateway.py','src/cacheflow/scheduler.py','src/cacheflow/prefix.py',
    'src/cacheflow/v3_residency.py','src/cacheflow/v3_memory_scheduler.py','src/cacheflow/v4_prepare.py']
for seed in [101,102,103]:
    runs={}
    for arm in arms:
        rid=f'v4-vllm-dev-{arm}-thread-qps4-s{seed}'
        run=load(rid);setup=json.loads(Path(f'results/v3/{rid}.setup.json').read_text())
        state=setup['gateway_before'];after=setup['gateway_after']
        assert state['completed_history_requests']==0 and state['active']==state['queue']==0
        assert state['prepare_mode']=='thread' and after['active']==after['queue']==0
        observer=after['residency']
        assert observer['known'] and observer['hash_contract_verified'] and observer['gaps']==0
        assert not setup['runtime']['profile'] and not setup['runtime']['kv_events'] and not setup['runtime']['batch_invariant']
        if reference_setup is None:reference_setup=setup
        for key in ['max_num_seqs','max_num_batched_tokens','kv_capacity_tokens','cpu_l1_gib','enforce_eager','prepare_in_thread']:
            assert setup['runtime'][key]==reference_setup['runtime'][key],key
        for path in relevant:
            assert setup['source_files_sha256'][path]==reference_setup['source_files_sha256'][path],path
        c=run['metrics']['counter_deltas']['vllm'];s=run['summary']
        assert s['requests']==s['successes']==60 and not s['errors']
        rows.append(dict(run_id=rid,seed=seed,arm=arm,requests=s['requests'],
            p50_ms=s['arrival_ttft_p50_ms'],p95_ms=s['arrival_ttft_p95_ms'],p99_ms=s['arrival_ttft_p99_ms'],
            computed_tokens=c['vllm:request_prefill_kv_computed_tokens_sum'],
            consumed_cpu_tokens=c['vllm:prompt_tokens_source_external_kv_transfer_total'],
            preemptions=c['vllm:num_preemptions_total'],admission=audit(rid)))
        runs[arm]=run
    for arm in arms[:-1]:
        pair=compare(runs[arm],runs['packing_reuse64'])
        # Keep the exact request contrasts and quality-hash differences; native
        # token-source metadata is already recorded per run above.
        pair.pop('a_metrics');pair.pop('b_metrics');pairs.append(pair)
aggregate=[]
for arm in arms:
    selected=[r for r in rows if r['arm']==arm]
    aggregate.append(dict(arm=arm,**{k:statistics.mean(r[k] for r in selected)
        for k in ['p50_ms','p95_ms','p99_ms','computed_tokens','consumed_cpu_tokens']}))
out=Path('results/v3/v4_vllm_dev_audit.json')
out.write_text(json.dumps(dict(scope='V4 dev:60 unique QA,3 serving seeds,18 complete runs; source accounting is vLLM-specific',
    requests=sum(r['requests'] for r in rows),errors=0,runs=rows,aggregate=aggregate,pairs=pairs),indent=2)+'\n')
for r in aggregate:print(r)
