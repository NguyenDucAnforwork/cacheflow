"""Supplemental full native baseline contrasts; never a candidate win.

The registered39 candidate pairs remain unchanged. This separate diagnostic
uses complete, hash-checked fresh-engine arms at one arrival seed only.
"""
import argparse
import json
from pathlib import Path
from v6_full_checkpoint import compare
from v6_raw_archive import expanded,sha


def analyze(checkpoint,output):
    checkpoint=Path(checkpoint);output=Path(output);assert not output.exists()
    cp=json.loads(checkpoint.read_text());assert cp['kind']=='interim_full_checkpoint_not_terminal_audit'
    runs={r['step']['arm']:r for r in cp['runs'] if r['step']['engine']=='sg' and r['step']['seed']==901 and r['step']['budget']==6}
    arms=['native_lpm','native_dfs','fifo64'];assert all(arm in runs for arm in arms)
    audits={};requests={};scores={};rows=[]
    for arm in arms:
        r=runs[arm];rid=r['run_id'];ap=Path(f'results/v3/{rid}.full_audit_r1.json');zp=Path(f'results/v3/{rid}.archive_r1.json')
        assert sha(ap)==r['audit_sha256'] and sha(zp)==r['archive_sha256']
        a=json.loads(ap.read_text());assert a['complete'] is True and a['requests']==1986 and a['errors']==0 and a['summary']==r['summary']
        with expanded(zp) as archive:
            assert archive['audit_sha256']==sha(ap) and {p['path']:p['sha256'] for p in archive['files']}==a['raw_sha256']
            rr=[json.loads(l) for l in Path(f'results/v3/raw/sglang/{rid}.jsonl').read_text().splitlines()]
            requests[arm]={p['request_id']:{k:p[k] for k in ['prompt_sha256','input_tokens','output_hash','sample_id','qa_index']} for p in rr}
        scores[arm]={p['request_id']:p for p in a['quality']['per_request']};audits[arm]=a
        counters=r['resource']['counter_deltas'];prompt=counters['sglang:prompt_tokens_total'];cached=counters['sglang:cached_tokens_total'];new=counters['sglang:uncached_prompt_tokens_histogram_sum']
        assert prompt==50522325 and cached+new==prompt
        c5=a['quality']['by_category']['5'];assert c5['n']==446
        rows.append(dict(arm=arm,run_id=rid,audit_sha256=sha(ap),archive_sha256=sha(zp),engine_pid=a['engine_pid'],
            ttft_s={q:r['summary']['arrival_ttft_'+q+'_ms']/1000 for q in ['p50','p95','p99']},makespan_s=r['summary']['duration_s'],
            new_prefill_tokens=new,cached_tokens=cached,answerable_f1=a['quality']['answerable_f1'],category5_correct=round(c5['mean']*446),
            output_budget_hits=a['quality']['output_budget_hits'],native_itl=r['native_itl'],resource=r['resource'],waits=r['waits']))
    contrasts=[]
    for aa,bb in [('native_lpm','native_dfs'),('native_lpm','fifo64'),('native_dfs','fifo64')]:
        pair=compare(audits[aa],audits[bb],requests[aa],requests[bb],scores[aa],scores[bb])
        # compare() uses generic candidate terminology; make the baseline-only
        # scope explicit here without relabelling either baseline as our method.
        pair['arm_a']=pair.pop('baseline');pair['arm_b']=pair.pop('candidate')
        pair['scope']='Supplemental baseline-to-baseline diagnostic, not a registered candidate contrast or new method'
        contrasts.append(pair)
    result=dict(kind='supplemental_full_native_baseline_diagnostic',complete_full_study=False,checkpoint_sha256=sha(checkpoint),source_sha256=sha(__file__),
        comparator_source_sha256=sha('scripts/v6_full_checkpoint.py'),seed=901,unique_qa=1986,measured_requests=5958,separate_warmup_requests=180,
        runs=rows,contrasts=contrasts,
        scope='Three completed native baseline arms, fresh engines and matched prompts/budgets/arrivals. No three-seed interval, candidate win, full39-pair replacement, quality equivalence or complete-Strata reproduction. Native direct versus gatewayFIFO changes admission, preparation and transport together; not an ordering-only causal contrast. Missing promotion/duration endpoints remain null; duration is not DMA time.')
    with output.open('x') as out:out.write(json.dumps(result,indent=2)+'\n')
    print('Checked three native baseline arms and three supplemental contrasts',flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('checkpoint',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();analyze(a.checkpoint,a.output)
