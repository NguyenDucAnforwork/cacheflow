import sys
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_native_resources import analyze


def test_optional_retract_gauge_missing_is_not_observed_zero():
    rows=[dict(timestamp_ns=t,gpu=dict(gpu_util_pct=1,power_w=100,vram_used_mib=10,temperature_c=50),summed_process_rss_bytes=100,
        sglang={'sglang:num_queue_reqs':q,'sglang:num_retracted_reqs':0,'sglang:hicache_host_total_tokens':108512})
        for t,q in [(1,0),(1_000_000_001,1)]]
    r=analyze(rows);assert r['retract_gauge_peak']==0 and r['retract_gauge_samples_observed']==2
    rows[0]['sglang'].pop('sglang:num_retracted_reqs');r=analyze(rows)
    assert r['retract_gauge_peak'] is None and r['retract_gauge_samples_observed']==1
    rows[0]['sglang'].pop('sglang:num_queue_reqs');r=analyze(rows)
    assert r['sampled_queue_above128_fraction'] is None and r['queue_samples_observed']==1
