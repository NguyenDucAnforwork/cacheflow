"""Three-seed audit of one complete control, while the whole native stage is live."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from v5_verify import verify
from v6_freeze_full import sha
from v6_native_contracts import configuration,ledger
from v6_native_metrics import summarize
from v6_analyze_fairness import analyze as fairness
from v5_analyze_histograms import analyze as histogram
from v5_analyze_decode import analyze as decode
from v5_analyze_waits import analyze as waits
from v5_run_intervals import paired_log_interval
from v6_native_resources import analyze as resources


def read(path):return json.loads(Path(path).read_text())


def main():
    p=argparse.ArgumentParser();p.add_argument('regime',choices=['dfs','lowload','lowreuse','gpufit','abstention']);a=p.parse_args()
    parent,seal=verify();base=Path('results/v3/sglang');raw=Path('results/v3/raw/sglang');rp=base/'v6native1_registration.json';reg=read(rp)
    for n,h in reg['source_sha256'].items():assert sha(n)==h,n
    blocks=[b for b in reg['blocks'] if b['regime']==a.regime];assert len(blocks)==3
    for block in blocks:
        for step in [block['warmup'],*block['actions']]:
            assert (raw/(step['run_id']+'.summary.json')).exists(),('Subset incomplete',step['run_id'])
            assert not (base/(step['run_id']+'.invalid')).exists()
    results=[];maps={};pids=[]
    for block in blocks:
        blockpids=set()
        for step in [block['warmup'],*block['actions']]:
            rid=step['run_id'];warm=rid==block['warmup']['run_id'];s,rows=ledger(rid,raw,step['requests']);setup=read(base/(rid+'.setup.json'))
            configuration(step,block,setup,s,parent,seal,reg,warm)
            manifest=read(Path(step['trace']).with_suffix('.manifest.json'))
            assert s['trace_sha256']==manifest['trace_sha256'] and sha(step['trace'])==reg['trace_sha256'][step['trace']]
            assert manifest['renderer_sha256']==seal['source_sha256']['src/cacheflow/v5_prompt.py'] and manifest['abstention_style']=='official_consistent_system_and_user'
            blockpids.add(s['engine_pid'])
            if warm:continue
            snapshotpath=base/(rid+'.itl_histogram.json');snapshot=read(snapshotpath);assert snapshot['request_file_sha256']==sha(raw/(rid+'.jsonl'))
            checked=summarize(rid,snapshot['before'],snapshot['after'],rows,s,'sglang');assert checked['coverage_valid']==snapshot['coverage_valid'] and checked['coverage_failures']==snapshot['coverage_failures']
            m=read(base/(rid+'.metrics_summary.json'));c=m['counter_deltas'];assert c['sglang:prompt_tokens_total']==sum(r['input_tokens'] for r in rows)
            assert c['sglang:cached_tokens_total']+c['sglang:uncached_prompt_tokens_histogram_sum']==sum(r['input_tokens'] for r in rows)
            resource=resources([json.loads(l) for l in (raw/(rid+'.metrics.jsonl')).read_text().splitlines()]);assert resource['host_capacity_tokens']*147456==16000745472
            maps[rid]={r['request_id']:r for r in rows};key='sglang:load_back_tokens_total'
            results.append(dict(**step,seed=block['seed'],regime=block['regime'],engine_pid=s['engine_pid'],
                **{k:s['arrival_ttft_'+k] for k in ['p50_ms','p95_ms','p99_ms']},computed_tokens=c['sglang:uncached_prompt_tokens_histogram_sum'],host_promoted_tokens=c.get(key),
                host_promotion_endpoints=dict(first=m['first_counter_endpoints'].get(key),last=m['last_counter_endpoints'].get(key)),
                resource=resource,actual_host_payload_bytes=resource['host_capacity_tokens']*147456,native_itl=histogram(snapshotpath),secondary=decode(rid),fairness=fairness(rid),waits=waits(dict(runs=[dict(run_id=rid,requests=step['requests'])])),
                setup_sha256=sha(base/(rid+'.setup.json')),request_file_sha256=sha(raw/(rid+'.jsonl'))))
        assert len(blockpids)==1;pids.extend(blockpids)
    assert len(set(pids))==3 and len(results)==9
    qp=base/f'v6native1_{a.regime}_subset_quality.json'
    subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir',str(raw),'--run-ids',*[r['run_id'] for r in results],'--output',str(qp)],check=True)
    quality={r['run_id']:r for r in read(qp)['runs']};by={r['run_id']:r for r in results};pairs=[];intervals=[]
    for r in results:r.update(f1=quality[r['run_id']]['answerable_f1'],by_category=quality[r['run_id']]['by_category'],output_budget_hits=quality[r['run_id']]['output_budget_hits'])
    for candidate,baseline in [('union64','native'),('packing_ready','native'),('packing_ready','union64')]:
        aa=[];bb=[]
        for seed in [101,102,103]:
            ar=next(r for r in results if r['seed']==seed and r['arm']==baseline);br=next(r for r in results if r['seed']==seed and r['arm']==candidate)
            arows=maps[ar['run_id']];brows=maps[br['run_id']];assert arows.keys()==brows.keys() and all(arows[k]['prompt_sha256']==brows[k]['prompt_sha256'] for k in arows)
            af,bf=ar['f1'],br['f1'];aa.append(ar);bb.append(br)
            pairs.append(dict(a=ar['run_id'],b=br['run_id'],baseline=baseline,candidate=candidate,seed=seed,
                **{k+'_delta_pct':100*(br[k]/ar[k]-1) for k in ['p50_ms','p95_ms','p99_ms']},
                f1_delta=bf-af if af is not None and bf is not None else None,
                category5_delta=(br['by_category']['5']['mean']-ar['by_category']['5']['mean']) if '5' in ar['by_category'] and '5' in br['by_category'] else None,
                output_hash_mismatches=sum(arows[k]['output_hash']!=brows[k]['output_hash'] for k in arows)))
        intervals.append(dict(baseline=baseline,candidate=candidate,metrics={k:paired_log_interval([r[k] for r in aa],[r[k] for r in bb]) for k in ['p50_ms','p95_ms','p99_ms']}))
    result=dict(subset_complete=True,overall_native_stage_complete=False,regime=blocks[0]['regime'],requests=sum(r['requests'] for r in results),errors=0,separate_warmup_requests=180,
        registration_sha256=sha(rp),quality_sha256=sha(qp),analysis_source_sha256={n:sha(n) for n in ['scripts/v6_audit_native_subset.py','scripts/v6_native_contracts.py','scripts/v6_native_resources.py']},runs=results,pairs=pairs,exploratory_intervals=intervals,
        scope='One complete9-arm control, three fresh native blocks; paired arms share process after flush/freshgateway. Exposed QA reused across schedules. Not the60-arm stage or full benchmark. n3interval assumptions unverified; no quality equivalence, missing-counter zero imputation or DMA-time interpretation.')
    path=base/f'v6native1_{blocks[0]["regime"]}_subset_audit.json';path.write_text(json.dumps(result,indent=2)+'\n')
    for pair in pairs:print(pair)


if __name__=='__main__':main()
