"""Require all eight prospective pilot arms before emitting paired findings."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import yaml
from v6_pilot import build_plan
from v5_verify import verify
from v3_analyze_runs import load,compare
from v5_analyze_decode import analyze as decode


def main():
    parent,seal=verify();reg_path=Path('results/v3/v6pilot2_registration.json');reg=json.loads(reg_path.read_text())
    assert reg['actions']==build_plan() and len(reg['actions'])==8
    assert reg['parent_v5_seal_sha256']==hashlib.sha256(Path('results/v3/v5_prompt_freeze.json').read_bytes()).hexdigest()
    for name,digest in reg['source_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest
    rows=[];loaded={};ids=[];secondary=[]
    expected={'fifo64':'fifo','union64':'packing_reuse','ready_fifo':'ready_fifo','packing_ready':'packing_ready'}
    for step in reg['actions']:
        rid=step['run_id'];run=load(rid);loaded[rid]=run;ids.append(rid);s=run['summary']
        setup=json.loads(Path(f'results/v3/{rid}.setup.json').read_text());cfg=yaml.safe_load(setup['gateway_config']);runtime=setup['runtime']
        entry=json.loads(Path(f'results/v3/{rid}.v6_entrypoint.json').read_text());m=json.loads(Path(step['trace']).with_suffix('.manifest.json').read_text())
        assert entry['source_sha256']==reg['source_sha256'] and 'cacheflow.v6_gateway:create_app' in entry['gateway_argv']
        assert entry['native_probe'] is False and entry['upstream_profile'] is False
        assert s['requests']==s['successes']==m['requests']==(60 if step['dataset']=='dev' else 40) and not s['errors']
        assert s['policy']==cfg['scheduler']['policy']==setup['gateway_before']['policy']==expected[step['arm']]
        assert s['trace_sha256']==m['trace_sha256'] and s['prompt_version']=='locomo-qwen-concise-v5'
        assert s['model_revision']==parent['model_revision'] and s['source_sha256']==parent['source_data_sha256'] and s['output_tokens_budget']==96
        assert s['request_read_timeout_s']==s['request_pool_timeout_s']==cfg['http_read_timeout_s']==180 and s['client_keepalive_connections']==0
        assert cfg['scheduler']['max_inflight']==64 and cfg['scheduler']['max_queue']==64 and cfg['residency']['max_bypasses']==8
        assert cfg['upstream_keepalive_connections']==0 and setup['gateway_before']['completed_history_requests']==0
        assert setup['gateway_before']['prepare_mode']=='thread' and runtime['residency_events'] and runtime['cpu_l1_bytes']==16000745472
        assert not any(runtime.get(k) for k in ['profile','kv_events','batch_invariant'])
        observer=setup['gateway_after']['residency'];assert observer['known'] and observer['hash_contract_verified'] and observer['gaps']==0
        snapshots=setup['source_files_sha256']
        for name,digest in parent['source_sha256'].items():assert snapshots[name]==digest,(rid,name)
        for name,digest in reg['source_sha256'].items():assert snapshots[name]==digest,(rid,name)
        stats=setup['gateway_after']['decision_stats']
        if step['arm'] in {'ready_fifo','packing_ready'}:assert 'readiness_gate' in stats and stats['readiness_blocked_decisions']>=0
        secondary.append(decode(rid))
        rows.append(dict(**step,requests=s['requests'],errors=0,engine_pid=s['engine_pid'],lmcache_pid=s['lmcache_pid'],
            **{key:s['arrival_ttft_'+key] for key in ['p50_ms','p95_ms','p99_ms']},
            source_counters=run['metrics']['counter_deltas']['vllm'],decision_stats=stats))
    quality_path=Path('results/v3/v6pilot2_quality.json')
    subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir','results/v3/raw','--run-ids',*ids,'--output',str(quality_path)],check=True)
    quality={r['run_id']:r for r in json.loads(quality_path.read_text())['runs']};pairs=[]
    for dataset,seed in [('dev',101),('stress',702)]:
        candidate=f'v6pilot2-{dataset}-packing_ready-s{seed}'
        for arm in ['fifo64','union64','ready_fifo']:
            baseline=f'v6pilot2-{dataset}-{arm}-s{seed}';p=compare(loaded[baseline],loaded[candidate]);p.pop('a_metrics');p.pop('b_metrics')
            p['p99_delta_pct']=100*(loaded[candidate]['summary']['arrival_ttft_p99_ms']/loaded[baseline]['summary']['arrival_ttft_p99_ms']-1)
            p.update(a_f1=quality[baseline]['answerable_f1'],b_f1=quality[candidate]['answerable_f1'],f1_delta=quality[candidate]['answerable_f1']-quality[baseline]['answerable_f1']);pairs.append(p)
    result=dict(scope='Complete prospective development pilot:60devQA at one arrival seed plus40previously exposed repairQA at another, not a fresh holdout, replicated confirmation or full benchmark. Native probe off. Host configured flags are shared; effective lazy heaps are recorded separately. First-text gate is not a physical pin/restore guarantee.',
        registration_sha256=hashlib.sha256(reg_path.read_bytes()).hexdigest(),requests=400,errors=0,runs=rows,pairs=pairs,secondary=secondary)
    Path('results/v3/v6pilot2_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in pairs:print(p['a'],'vs',p['b'],'p95 delta',p['p95_delta_pct'],'F1 delta',p['f1_delta'])


if __name__=='__main__':main()
