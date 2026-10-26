import copy
import sys
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_native_metrics import summarize


def fixture():
    keys=['prompt_tokens_total','generation_tokens_total','inter_token_latency_seconds_count','inter_token_latency_seconds_sum']
    before=dict(pid=7,start_ns=1,end_ns=2,counters={'sglang:'+k:0 for k in keys},itl_cumulative_buckets={'0.1':0,'+Inf':0})
    after=dict(pid=7,start_ns=5,end_ns=6,counters=dict(zip(['sglang:'+k for k in keys],[10,3,2,0.1])),itl_cumulative_buckets={'0.1':2,'+Inf':2})
    rows=[dict(scheduled_arrival_ns=3,complete_ns=4,input_tokens=10,output_tokens=3,status='ok')]
    return before,after,rows,dict(engine_pid=7)


def test_native_coverage_and_mean():
    result=summarize('x',*fixture(),'sglang')
    assert result['coverage_valid'] and result['native_itl_mean_ms']==50


def test_native_missing_reset_window_and_tokens_fail_closed():
    for mutate in [lambda b,a,r,s:a.update(pid=8),lambda b,a,r,s:b.update(end_ns=3),
        lambda b,a,r,s:a.update(start_ns=4),lambda b,a,r,s:a['counters'].pop('sglang:generation_tokens_total'),
        lambda b,a,r,s:r[0].update(output_tokens=4),lambda b,a,r,s:a['itl_cumulative_buckets'].update({'0.1':-1}),
        lambda b,a,r,s:a['itl_cumulative_buckets'].pop('0.1'),
        lambda b,a,r,s:a['itl_cumulative_buckets'].update({'0.1':3}),
        lambda b,a,r,s:a['counters'].update({'sglang:inter_token_latency_seconds_sum':float('nan')}),
        lambda b,a,r,s:a.update(error='capture failed')]:
        args=copy.deepcopy(fixture());mutate(*args)
        result=summarize('x',*args,'sglang')
        assert not result['coverage_valid'] and result['native_itl_mean_ms'] is None
    b,a,r,s=fixture()
    assert not summarize('empty',b,a,[],s,'sglang')['coverage_valid']
