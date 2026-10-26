"""Require every V5 protocol-repair repeat before launching the full study."""
import json
import subprocess
import sys
from pathlib import Path
from v5_confirm import build_plan
from v5_verify import verify
from v5_audit_contracts import audit_common
from v4_audit_sglang_runs import audit as audit_sg
from v3_analyze_runs import load as load_main,compare as compare_main
from v4_compare_sglang import compare as compare_sg
from cacheflow.v4_resources import sglang_host_pool_bytes

def main():
    freeze,seal=verify();digest=seal['parent_method_freeze_sha256'];rows=[];sg_ids=[];main_ids=[];lookup={}
    steps=[s for s in build_plan() if s['kind'] in {'sg','main'} and '-warm-' not in s['run_id']]
    assert len(steps)==27
    for step in steps:
        rid=step['run_id'];lookup[rid]=step
        m=json.loads(Path(step['trace']).with_suffix('.manifest.json').read_text())
        assert m['requests']==40 and m['parent_method_freeze_sha256']==digest
        root=Path('results/v3/sglang' if step['kind']=='sg' else 'results/v3')
        raw=Path('results/v3/raw/sglang' if step['kind']=='sg' else 'results/v3/raw')
        captured=json.loads((root/f'{rid}.setup.json').read_text())
        summary=json.loads((raw/f'{rid}.summary.json').read_text())
        audit_common(step,captured,summary,m,freeze,seal)
        if step['kind']=='sg':
            row=audit_sg(rid);sg_ids.append(rid)
            assert row['runtime']['same_batch_guard'] and not row['runtime']['profile_transfers']
            assert sglang_host_pool_bytes(row['runtime']['host_kv_gib'],147456)==freeze['host_pool_bytes']['dev_and_confirmation']
            assert row['trace_sha256']==m['trace_sha256'] and row['requests']==40
            rows.append(row)
        else:
            run=load_main(rid);setup=json.loads(Path(f'results/v3/{rid}.setup.json').read_text());main_ids.append(rid)
            assert setup['gateway_before']['completed_history_requests']==0 and setup['gateway_before']['prepare_mode']=='thread'
            assert setup['runtime']['cpu_l1_bytes']==freeze['host_pool_bytes']['dev_and_confirmation']
            argv=setup['actual_lmcache_argv_list'];actual=int(float(argv[argv.index('--l1-size-gb')+1])*2**30)
            assert actual==freeze['host_pool_bytes']['dev_and_confirmation']
            s=run['summary'];assert s['requests']==s['successes']==40 and not s['errors'] and s['trace_sha256']==m['trace_sha256']
            rows.append(dict(run_id=rid,requests=40,engine_kind='vllm',p50_ms=s['arrival_ttft_p50_ms'],
                p95_ms=s['arrival_ttft_p95_ms'],p99_ms=s['arrival_ttft_p99_ms'],runtime=setup['runtime']))
    for kind,ids,raw in [('sg',sg_ids,'results/v3/raw/sglang'),('main',main_ids,'results/v3/raw')]:
        subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir',raw,'--run-ids',*ids,
            '--output',f'results/v3/v5r2_confirmation_{kind}_quality.json'],check=True)
    sq={r['run_id']:r for r in json.loads(Path('results/v3/v5r2_confirmation_sg_quality.json').read_text())['runs']}
    pairs=[]
    for qps in [4,2]:
        for seed in [701,702,703]:
            prefix=f'v5r2-confirm-sg-lpm-qps{qps}'
            for arm in (['native','fifo'] if qps==4 else ['native']):
                pairs.append(compare_sg(f'{prefix}-{arm}-s{seed}',f'{prefix}-union-s{seed}',sq))
    for seed in [701,702,703]:
        for arm in ['fifo64','bundle16']:
            p=compare_main(load_main(f'v5r2-confirm-main-qps4-{arm}-s{seed}'),load_main(f'v5r2-confirm-main-qps4-union64-s{seed}'))
            p.pop('a_metrics');p.pop('b_metrics');pairs.append(p)
    result=dict(scope='V5 protocol-repair repeats:40 QA previously exposed under V4,3 serving schedules; not fresh semantic holdout; DFS is a fresh-process competitor',
        method_freeze_sha256=digest,requests=sum(r['requests'] for r in rows),errors=0,runs=rows,pairs=pairs)
    Path('results/v3/v5r2_confirmation_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Complete frozen confirmation',result['requests'],'requests',len(rows),'runs',flush=True)


if __name__=='__main__':main()
