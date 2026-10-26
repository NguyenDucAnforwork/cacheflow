"""Require all V5 fixed-method dev, control and abstention runs; no aliases."""
import json
import subprocess
import sys
from pathlib import Path
import yaml
from v5_validate import build_plan
from v5_verify import verify
from v4_audit_sglang_runs import audit as sg_audit
from v4_compare_sglang import compare as sg_compare
from v3_analyze_runs import load as main_load,compare as main_compare
from v3_audit_admission import audit as admission_audit


def main():
    parent,seal=verify();steps=[s for s in build_plan() if s['kind'] in {'sg','main'} and '-warm-' not in s['run_id']]
    assert len(steps)==57;rows=[];ids={'sg':[],'main':[]}
    for step in steps:
        rid=step['run_id'];kind=step['kind'];ids[kind].append(rid)
        base=Path('results/v3/sglang' if kind=='sg' else 'results/v3');raw=Path('results/v3/raw/sglang' if kind=='sg' else 'results/v3/raw')
        setup=json.loads((base/f'{rid}.setup.json').read_text());s=json.loads((raw/f'{rid}.summary.json').read_text())
        m=json.loads(Path(step['trace']).with_suffix('.manifest.json').read_text());runtime=setup['runtime']
        assert s['requests']==s['successes']==m['requests'] and not s['errors'] and s['trace_sha256']==m['trace_sha256']
        assert s['prompt_version']==m['prompt_version']=='locomo-qwen-concise-v5'
        assert s['request_read_timeout_s']==s['request_pool_timeout_s']==3600
        assert s['client_keepalive_connections']==0
        if kind=='sg':
            row=sg_audit(rid)
            assert runtime['same_batch_guard'] and not runtime['profile_transfers'] and runtime['host_kv_gib']==16
            assert runtime['io_backend']=='direct' and runtime['gpu_kv_gib']==(10 if '-g10-' in rid else 6)
            assert runtime['schedule_policy']==('dfs-weight' if '-dfs-' in rid else 'lpm')
            expected={'native':None,'fifo':'fifo','union':'packing_reuse'}[step['arm']]
            assert setup['gateway_policy']==expected
            cap=64
        else:
            run=main_load(rid);expected,cap={'fifo16':('fifo',16),'fifo64':('fifo',64),'lpm16':('lpm_real',16),
                'bundle16':('bundle_wave',16),'dhas16':('dhas',16),'union64':('packing_reuse',64)}[step['arm']]
            assert runtime['cpu_l1_bytes']==parent['host_pool_bytes']['dev_and_confirmation']
            assert runtime['residency_events'] and not runtime['profile'] and not runtime['kv_events'] and not runtime['batch_invariant']
            obs=setup['gateway_after']['residency'];assert obs['known'] and obs['hash_contract_verified'] and obs['gaps']==0
            row=dict(run_id=rid,requests=s['requests'],**{k:s['arrival_ttft_'+k] for k in ['p50_ms','p95_ms','p99_ms']},
                admission=admission_audit(rid),source_counters=run['metrics']['counter_deltas']['vllm'])
        if expected:
            cfg=yaml.safe_load(setup['gateway_config']);before=setup['gateway_before']
            assert cfg['scheduler']['policy']==before['policy']==expected and cfg['scheduler']['max_inflight']==cap
            assert cfg['scheduler']['max_queue']==64 and cfg['residency']['max_bypasses']==8
            assert cfg['http_read_timeout_s']==before['upstream_read_timeout_s']==3600
            assert before['prepare_mode']=='thread' and before['active']==before['queue']==before['completed_history_requests']==0
        rows.append(row)
    quality={}
    for kind in ids:
        out=Path(f'results/v3/v5r2_validation_{kind}_quality.json')
        subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir',
            'results/v3/raw/sglang' if kind=='sg' else 'results/v3/raw','--run-ids',*ids[kind],'--output',str(out)],check=True)
        quality[kind]={r['run_id']:r for r in json.loads(out.read_text())['runs']}
    pairs=[]
    for regime,budget,qps in [('lpm',6,4),('lpm',6,2),('dfs',6,4),('gpufit',10,4),('lowreuse',6,4),('abstention',6,4)]:
        for seed in [101,102,103]:
            prefix=f'v5r2-dev-{regime}-g{budget}-qps{qps}'
            for arm in (['native','fifo'] if regime=='lpm' and qps==4 else ['native']):
                pairs.append(sg_compare(f'{prefix}-{arm}-s{seed}',f'{prefix}-union-s{seed}',quality['sg']))
    for seed in [101,102,103]:
        for arm in ['fifo16','fifo64','lpm16','bundle16','dhas16']:
            pair=main_compare(main_load(f'v5r2-dev-main-qps4-{arm}-s{seed}'),main_load(f'v5r2-dev-main-qps4-union64-s{seed}'))
            pair.pop('a_metrics');pair.pop('b_metrics');pairs.append(pair)
    low=[p for p in pairs if '-lowreuse-' in p['a']]
    result=dict(scope='V5 consistent-prompt fixed-method validation; repeated serving schedules reuse QA; no source or method tuning from these results',
        requests=sum(r['requests'] for r in rows),errors=0,runs=rows,pairs=pairs,
        low_reuse_gate_passed=all(p['p95_ms_delta_pct']<=5 for p in low))
    assert result['requests']==2820
    Path('results/v3/v5r2_validation_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Audited V5 validation',result['requests'],'requests; low-reuse gate',result['low_reuse_gate_passed'],flush=True)


if __name__=='__main__':main()
