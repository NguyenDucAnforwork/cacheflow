"""Audit completed SG portion of repair repeats; never substitutes for all27 runs."""
import json
import subprocess
import sys
from pathlib import Path
from v5_confirm import build_plan
from v5_verify import verify
from v5_audit_contracts import audit_common
from v4_audit_sglang_runs import audit
from v4_compare_sglang import compare,quality_contrast


def main():
    parent,seal=verify();steps=[s for s in build_plan() if s['kind']=='sg' and '-warm-' not in s['run_id']]
    assert len(steps)==18;rows=[];setups={}
    for step in steps:
        rid=step['run_id'];base=Path('results/v3/sglang');raw=Path('results/v3/raw/sglang')
        setup=json.loads((base/f'{rid}.setup.json').read_text());setups[rid]=setup
        summary=json.loads((raw/f'{rid}.summary.json').read_text());manifest=json.loads(Path(step['trace']).with_suffix('.manifest.json').read_text())
        audit_common(step,setup,summary,manifest,parent,seal);assert summary['requests']==40
        rows.append(audit(rid))
    quality_path=Path('results/v3/v5r2_sg_repair_repeats_quality.json')
    subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir','results/v3/raw/sglang','--run-ids',*[s['run_id'] for s in steps],'--output',str(quality_path)],check=True)
    quality={r['run_id']:r for r in json.loads(quality_path.read_text())['runs']};by={r['run_id']:r for r in rows};pairs=[]
    for qps in [4,2]:
        for seed in [701,702,703]:
            b=f'v5r2-confirm-sg-lpm-qps{qps}-union-s{seed}'
            for arm in (['native','fifo'] if qps==4 else ['native']):pairs.append(compare(f'v5r2-confirm-sg-lpm-qps{qps}-{arm}-s{seed}',b,quality))
            if qps==4:
                a=f'v5r2-confirm-sg-dfs-qps4-native-s{seed}';sa=setups[a];sb=setups[b]
                ra=dict(sa['runtime']);rb=dict(sb['runtime']);ra.pop('schedule_policy');rb.pop('schedule_policy');assert ra==rb
                assert sa['upstream_source_sha256']==sb['upstream_source_sha256'] and by[a]['trace_sha256']==by[b]['trace_sha256']
                raw=Path('results/v3/raw/sglang');aa={r['request_id']:r for r in map(json.loads,(raw/f'{a}.jsonl').read_text().splitlines())};bb={r['request_id']:r for r in map(json.loads,(raw/f'{b}.jsonl').read_text().splitlines())}
                assert aa.keys()==bb.keys() and all(aa[k]['prompt_sha256']==bb[k]['prompt_sha256'] for k in aa)
                pairs.append(dict(a=a,b=b,process_scope='fresh-process nativeDFS competitor',
                    **{k+'_delta_pct':100*(by[b][k]/by[a][k]-1) for k in ['p50_ms','p95_ms','p99_ms']},
                    **quality_contrast(quality[a],quality[b]),output_hash_mismatches=sum(aa[k]['output_hash']!=bb[k]['output_hash'] for k in aa)))
    out=dict(scope='Completed nativeSG portion only:18runs720requests,40uniqueQA previously exposed underV4,three arrival schedules. Main repeats incomplete; not a complete27-run stage, fresh semantic holdout or full study.',
        parent_method_freeze_sha256=seal['parent_method_freeze_sha256'],requests=720,errors=0,runs=rows,pairs=pairs)
    Path('results/v3/v5r2_sg_repair_repeats_audit.json').write_text(json.dumps(out,indent=2)+'\n')
    for p in pairs:print(p['a'],round(p['p95_ms_delta_pct'],3),round(p['f1_delta'],6))


if __name__=='__main__':main()
