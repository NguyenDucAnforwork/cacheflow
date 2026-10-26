import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_main_resources import analyze


def test_resource_weights_and_missing_counter_not_zero():
    rows=[dict(timestamp_ns=t,gpu=dict(gpu_util_pct=v,power_w=100,vram_used_mib=10),vllm=c,lmcache={},process={})
        for t,v,c in [(0,10,{'x_total':1}),(1_000_000_000,30,{'x_total':2}),(4_000_000_000,99,{'x_total':4,'late_total':5})]]
    r=analyze(rows);assert r['gpu_time_weighted_util_pct']==25
    assert r['strict_counter_deltas']['vllm']['x_total']==3 and r['strict_counter_deltas']['vllm']['late_total'] is None
    rows[1]['gpu'].pop('power_w');assert analyze(rows)['gpu_time_weighted_power_w'] is None
    rows[-1]['timestamp_ns']=0
    with pytest.raises(AssertionError):analyze(rows)
