"""Audit each completed fixed control block, with category5 separate from F1."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from v5_verify import verify
from v4_audit_sglang_runs import audit
from v4_compare_sglang import compare


def main():
    p=argparse.ArgumentParser();p.add_argument('regime',choices=['lowload','lowreuse','abstention','gpufit','dfs']);a=p.parse_args()
    verify();regime,qps,budget={'lowload':('lpm',2,6),'lowreuse':('lowreuse',4,6),'abstention':('abstention',4,6),
        'gpufit':('gpufit',4,10),'dfs':('dfs',4,6)}[a.regime]
    prefix=f'v5r2-dev-{regime}-g{budget}-qps{qps}'
    ids=[f'{prefix}-{arm}-s{seed}' for seed in [101,102,103] for arm in ['native','union']]
    expected=8 if regime=='lowreuse' else 12 if regime=='abstention' else 60
    rows=[]
    for rid in ids:
        row=audit(rid);assert row['requests']==expected and row['prompt_version']=='locomo-qwen-concise-v5'
        s=json.loads(Path(f'results/v3/raw/sglang/{rid}.summary.json').read_text())
        assert s['client_keepalive_connections']==0 and s['request_read_timeout_s']==s['request_pool_timeout_s']==3600
        rows.append(row)
    out=Path(f'results/v3/v5r2_{a.regime}_quality.json')
    subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir','results/v3/raw/sglang',
        '--run-ids',*ids,'--output',str(out)],check=True)
    quality={r['run_id']:r for r in json.loads(out.read_text())['runs']}
    pairs=[compare(f'{prefix}-native-s{seed}',f'{prefix}-union-s{seed}',quality) for seed in [101,102,103]]
    result=dict(scope='V5 revision2 named control only; repeated schedules do not add unique QA. No template causal claim against differently batched V4 full data.',
        regime=a.regime,requests=sum(r['requests'] for r in rows),errors=0,runs=rows,pairs=pairs)
    if regime=='lowreuse':result['declared_p95_gate_passed']=all(r['p95_ms_delta_pct']<=5 for r in pairs)
    Path(f'results/v3/v5r2_{a.regime}_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    for r in pairs:print(r['a'],r['p95_ms_delta_pct'],r['f1_delta'],r['category5_delta'])


if __name__=='__main__':main()
