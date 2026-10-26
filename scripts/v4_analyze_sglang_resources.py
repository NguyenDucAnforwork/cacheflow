"""Analyze existing native samples; live snapshots require a verified replay PID.

A sampled queue>128 is evidence of the LPM fallback condition, not an exact
scheduler-decision trace. Time-weighted GPU observations are sample estimates.
"""
import argparse
import hashlib
import json
from pathlib import Path
import psutil


def analyze(samples):
    assert len(samples)>1
    stamps=[r['timestamp_ns'] for r in samples]
    assert all(b>a for a,b in zip(stamps,stamps[1:]))
    weights=[(b-a)/1e9 for a,b in zip(stamps,stamps[1:])]
    elapsed=sum(weights)
    def delta(name):
        a=samples[0]['sglang'].get(name);b=samples[-1]['sglang'].get(name)
        if a is None or b is None:return None
        assert b>=a,(name,a,b)
        return b-a
    queue=[r['sglang'].get('sglang:num_queue_reqs') for r in samples]
    above=sum(w for r,w in zip(samples,weights) if (r['sglang'].get('sglang:num_queue_reqs') or 0)>128)
    def weighted_gpu(name):
        values=[(r['gpu'].get(name),w) for r,w in zip(samples,weights)]
        if any(v is None for v,w in values):return None
        return sum(v*w for v,w in values)/elapsed
    def peak_gpu(name):
        v=[r['gpu'].get(name) for r in samples]
        return max(x for x in v if x is not None) if any(x is not None for x in v) else None
    counters={name:delta(name) for name in ['sglang:num_requests_total','sglang:prompt_tokens_total',
        'sglang:cached_tokens_total','sglang:uncached_prompt_tokens_histogram_sum','sglang:load_back_tokens_total',
        'sglang:load_back_duration_seconds_sum','sglang:process_cpu_seconds_total',
        'sglang:queue_time_seconds_sum','sglang:time_to_first_token_seconds_sum','sglang:num_retracted_requests_total']}
    return dict(samples=len(samples),window_s=elapsed,start_ns=stamps[0],end_ns=stamps[-1],
        counter_deltas=counters,
        endpoint_counters={name:{'first':samples[0]['sglang'].get(name),'last':samples[-1]['sglang'].get(name)} for name in
            ['sglang:load_back_tokens_total','sglang:load_back_duration_seconds_sum','sglang:num_retracted_requests_total']},
        retract_gauge_peak=max(r['sglang'].get('sglang:num_retracted_reqs',0) for r in samples),queue_peak=max(v for v in queue if v is not None),queue_last=queue[-1],
        sampled_queue_above128_s=above,sampled_queue_above128_fraction=above/elapsed,
        gpu_time_weighted_util_pct=weighted_gpu('gpu_util_pct'),gpu_time_weighted_power_w=weighted_gpu('power_w'),
        vram_peak_mib=peak_gpu('vram_used_mib'),temperature_peak_c=peak_gpu('temperature_c'),
        summed_process_rss_peak_bytes=max(r['summed_process_rss_bytes'] for r in samples),
        last_host_used_tokens=samples[-1]['sglang'].get('sglang:hicache_host_used_tokens'),
        host_capacity_tokens=samples[-1]['sglang'].get('sglang:hicache_host_total_tokens'))


def main():
    p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument('--live-pid',type=int)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.live_pid:
        process=psutil.Process(a.live_pid)
        cmd=process.cmdline();assert process.is_running() and 'cacheflow.v2_replay' in cmd and a.run_id in cmd
    base=Path('results/v3/raw/sglang');path=base/f'{a.run_id}.metrics.jsonl'
    if not a.live_pid:
        summary=json.loads((base/f'{a.run_id}.summary.json').read_text())
        assert not summary['errors'] and summary['requests']==summary['successes']
    raw=path.read_bytes();lines=raw.splitlines(keepends=True)
    if a.live_pid and lines and not lines[-1].endswith(b'\n'):lines=lines[:-1]
    samples=[json.loads(line) for line in lines]
    result=dict(run_id=a.run_id,live_snapshot=bool(a.live_pid),
        source_prefix_sha256=hashlib.sha256(b''.join(lines)).hexdigest(),
        scope='Existing 1Hz observations, left-endpoint weighted. Live snapshots are incomplete and not performance results. Summed RSS double-counts shared pages; load_back CPU duration is enqueue-path time, not DMA. Missing endpoint counters remain null.',
        **analyze(samples))
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
