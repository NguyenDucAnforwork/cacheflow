"""Pair aggregation fixtures preserve unfavorable metrics and per-QA changes."""
import copy
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v10_audit_epoch_dev import compare


def projected_pair():
    rid='v6dev1-main-union64-s101'
    summary=json.loads(Path('results/v3/raw',rid+'.summary.json').read_text())
    q=next(r for r in json.loads(Path('results/v3/v6dev1_main_quality.json').read_text())['runs'] if r['run_id']==rid)
    requests={r['request_id']:r for r in map(json.loads,Path('results/v3/raw',rid+'.jsonl').read_text().splitlines())}
    convs={r['sample_id'] for r in requests.values()}
    a=dict(run_id='cpu-projected-reference',step=dict(engine='main',seed=101,arm='union64'),engine_pid=1,lmcache_pid=2,
        summary=summary,quality=q,secondary=dict(completion_latency_ms=dict(p95=100.)),
        fairness=dict(by_conversation=[dict(sample_id=c,arrival_ttft_ms=dict(p95=100.)) for c in sorted(convs)]))
    b=copy.deepcopy(a);b.update(run_id='cpu-projected-epoch',engine_pid=3,lmcache_pid=4);b['step']['arm']='epoch_union64'
    for key,factor in [('arrival_ttft_p50_ms',1.2),('arrival_ttft_p95_ms',.9),('arrival_ttft_p99_ms',.8)]:b['summary'][key]*=factor
    return a,b,requests,copy.deepcopy(requests)


def test_equal_quality_mean_does_not_hide_individual_changes_or_median_regression():
    a,b,ar,br=projected_pair()
    candidates=[(i,j) for i,r in enumerate(b['quality']['per_request']) for j,s in enumerate(b['quality']['per_request']) if r['category']==s['category'] and r['score']<s['score']]
    i,j=candidates[0];aa=b['quality']['per_request'][i];bb=b['quality']['per_request'][j];aa['score'],bb['score']=bb['score'],aa['score']
    br[aa['request_id']]['output_hash']='projected-changed';br[bb['request_id']]['output_hash']='projected-changed'
    p=compare(a,b,ar,br)
    assert p['p50_ms_delta_pct']==pytest.approx(20) and p['p95_ms_delta_pct']==pytest.approx(-10)
    assert p['f1_delta']==0 and p['output_hash_mismatches']==2
    assert sum(r['improved'] for r in p['per_category_score_changes'].values())==1
    assert sum(r['decreased'] for r in p['per_category_score_changes'].values())==1


@pytest.mark.parametrize('bad',['prompt','category','engine','cache'])
def test_changed_pair_identity_or_retained_process_is_rejected(bad):
    a,b,ar,br=projected_pair()
    if bad=='prompt':br[next(iter(br))]['prompt_sha256']='different'
    elif bad=='category':b['quality']['per_request'][0]['category']=99
    elif bad=='engine':b['engine_pid']=a['engine_pid']
    else:b['lmcache_pid']=a['lmcache_pid']
    with pytest.raises(AssertionError):compare(a,b,ar,br)


def test_cpu_cost_change_does_not_hide_worse_median_or_missing_external_metric():
    a,b,ar,br=projected_pair()
    a['gateway_decision_stats']=dict(cpu_ms=100,calls=1000,cache_hits=990)
    b['gateway_decision_stats']=dict(cpu_ms=10,calls=1200,cache_hits=1190)
    result=compare(a,b,ar,br)
    assert result['scheduler_decision_stats']['cpu_ms_delta']==-90
    assert result['p50_ms_delta_pct']==pytest.approx(20)
    assert result['source_work']['candidate']['engine_consumed_external_tokens'] is None
