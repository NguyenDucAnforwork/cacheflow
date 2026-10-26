from importlib.util import spec_from_file_location,module_from_spec
import pytest


def load(name):
    spec=spec_from_file_location(name,'scripts/'+name+'.py');m=module_from_spec(spec);spec.loader.exec_module(m);return m


def test_decode_proxy_excludes_single_token_and_includes_response_close_overhead():
    m=load('v5_analyze_decode')
    rows=[dict(status='ok',scheduled_arrival_ns=0,first_token_ns=1_000_000,complete_ns=5_000_000,output_tokens=1),
          dict(status='ok',scheduled_arrival_ns=0,first_token_ns=2_000_000,complete_ns=8_000_000,output_tokens=3)]
    s=m.summarize(rows,1)
    assert s['proxy_eligible_requests']==1 and s['single_token_responses']==1
    assert s['client_tpot_proxy_ms']['p50']==3 and s['generated_tokens']==4


def test_log_ratio_interval_requires_three_units_and_preserves_equal_ratios():
    m=load('v5_run_intervals')
    assert m.paired_log_interval([1],[2]) is None
    r=m.paired_log_interval([1,2,4],[2,4,8])
    assert r['geometric_ratio_delta_pct']==pytest.approx(100)
    assert r['exploratory_t95_low_pct']==pytest.approx(100) and r['exploratory_t95_high_pct']==pytest.approx(100)
    with pytest.raises(AssertionError):m.paired_log_interval([0,1,2],[1,2,3])


def test_histogram_bounds_reject_missing_or_nonmonotonic_coverage():
    m=load('v5_analyze_histograms')
    b={'0.01':2,'0.1':9,'+Inf':10}
    r=m.quantile_bounds(b,10,.95)
    assert r['lower_ms']==100 and r['upper_ms'] is None and r['upper_unbounded']
    assert m.quantile_bounds(b,10,.5)['upper_ms']==100
    with pytest.raises(AssertionError):m.quantile_bounds({'0.1':10},10,.95)
    with pytest.raises(AssertionError):m.quantile_bounds({'0.01':9,'0.1':2,'+Inf':10},10,.95)
