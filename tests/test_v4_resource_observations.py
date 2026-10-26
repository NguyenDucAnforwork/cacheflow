from importlib.util import spec_from_file_location,module_from_spec
import pytest

spec=spec_from_file_location('v4_resource_observations','scripts/v4_analyze_sglang_resources.py')
module=module_from_spec(spec);spec.loader.exec_module(module)


def sample(seconds,queue,util,requests,loads=None):
    counters={'sglang:num_queue_reqs':queue,'sglang:num_requests_total':requests}
    if loads is not None:counters['sglang:load_back_tokens_total']=loads
    return dict(timestamp_ns=int(seconds*1e9),sglang=counters,
        gpu=dict(gpu_util_pct=util,power_w=200,vram_used_mib=16000,temperature_c=60),
        summed_process_rss_bytes=50_000_000_000)


def test_irregular_samples_are_time_weighted_and_missing_first_counter_stays_unknown():
    result=module.analyze([sample(0,200,100,10),sample(1,0,0,11),sample(4,200,100,13,1000)])
    assert result['window_s']==4
    assert result['gpu_time_weighted_util_pct']==25
    assert result['sampled_queue_above128_fraction']==.25
    assert result['counter_deltas']['sglang:num_requests_total']==3
    assert result['counter_deltas']['sglang:load_back_tokens_total'] is None


def test_counter_reset_or_nonmonotonic_clock_cannot_silently_become_work_savings():
    with pytest.raises(AssertionError):module.analyze([sample(0,0,0,10),sample(1,0,0,9)])
    with pytest.raises(AssertionError):module.analyze([sample(1,0,0,10),sample(1,0,0,11)])
