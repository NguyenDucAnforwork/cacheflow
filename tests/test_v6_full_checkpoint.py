"""Interim pair eligibility and actual full graph; no inference or new results."""
import copy
import json
import sys
from pathlib import Path
from collections import Counter
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_full_checkpoint import compare,planned_pairs
from v6_full_plan import build_plan


def test_primary_pair_graph_has_all_registered_baselines_without_cross_matching():
    plan={s['run_id']:s for s in build_plan()};pairs=planned_pairs()
    assert len(pairs)==len(set(pairs))==39
    counts=Counter()
    for a,b in pairs:
        aa=plan[a];bb=plan[b]
        assert (aa['engine'],aa['budget'],aa['seed'])==(bb['engine'],bb['budget'],bb['seed'])
        counts[(aa['engine'],aa['budget'],aa['seed'])]+=1
        assert bb['arm'] in {'union64','packing_ready'}
    assert counts[('main',6,901)]==5 and counts[('sg',6,901)]==7 and counts[('sg',10,901)]==3
    assert ('v6full1-main-g6-bundle16-s903','v6full1-main-g6-union64-s903') in pairs
    assert ('v6full1-sg-g6-native_dfs-s902','v6full1-sg-g6-packing_ready-s902') in pairs


def pair_fixture():
    a=json.loads(Path('results/v3/v6full1-main-g6-fifo64-s901.full_audit_r1.json').read_text());b=copy.deepcopy(a)
    b['run_id']='projected-bundle';b['step']['arm']='bundle16';b['engine_pid']+=1;b['lmcache_pid']+=1
    for key in ['arrival_ttft_p50_ms','arrival_ttft_p95_ms','arrival_ttft_p99_ms']:b['summary'][key]*=.75
    ar={r['request_id']:dict(prompt_sha256='same-prompt',input_tokens=10,output_hash='same-output',sample_id=r['sample_id'],qa_index=i) for i,r in enumerate(a['quality']['per_request'])}
    br=copy.deepcopy(ar);aq={r['request_id']:r for r in a['quality']['per_request']};bq=copy.deepcopy(aq)
    return a,b,ar,br,aq,bq


def test_pair_keeps_hash_and_quality_changes_in_addition_to_latency():
    args=pair_fixture();first=next(iter(args[3]));args[3][first]['output_hash']='different'
    args[5][first]['score']=args[4][first]['score']+1
    result=compare(*args)
    assert result['p95_ms_delta_pct']==-25 and result['output_hash_mismatches']==1
    category=str(args[4][first]['category']);assert result['per_category_score_changes'][category]['improved']==1


def test_partial_mismatched_or_retained_process_pairs_are_rejected():
    for mutate in [lambda x:x[3].pop(next(iter(x[3]))),
                   lambda x:x[3][next(iter(x[3]))].update(prompt_sha256='different-same-length'),
                   lambda x:x[1]['step'].update(seed=902),
                   lambda x:x[1].update(engine_pid=x[0]['engine_pid']),
                   lambda x:x[1].update(lmcache_pid=x[0]['lmcache_pid'])]:
        args=list(pair_fixture());mutate(args)
        with pytest.raises(AssertionError):compare(*args)
