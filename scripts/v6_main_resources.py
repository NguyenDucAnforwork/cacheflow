"""Summarize retained main-stack samples; no new endpoint queries."""
import math


def analyze(samples):
    assert len(samples)>=2
    times=[s['timestamp_ns'] for s in samples]
    weights=[(b-a)/1e9 for a,b in zip(times,times[1:])];assert all(w>0 for w in weights)
    duration=sum(weights)
    def weighted(values):
        return sum(v*w for v,w in zip(values,weights))/duration if all(v is not None and math.isfinite(v) for v in values) else None
    def peak(values):return max(values) if values and all(v is not None for v in values) else None
    process={}
    for source in ['vllm','lmcache']:
        start=samples[0].get('process',{}).get(source,{});end=samples[-1].get('process',{}).get(source,{})
        a=start.get('cpu_seconds');b=end.get('cpu_seconds')
        process[source]=dict(sampled_cpu_seconds=b-a if a is not None and b is not None and b>=a else None,
            summed_rss_peak_bytes=peak([s.get('process',{}).get(source,{}).get('rss_bytes') for s in samples]),
            processes_peak=peak([s.get('process',{}).get(source,{}).get('processes') for s in samples]))
    strict={}
    for source in ['vllm','lmcache']:
        first=samples[0].get(source,{});last=samples[-1].get(source,{})
        values={}
        for name in first.keys()|last.keys():
            if not name.endswith(('_total','_sum','_count')):continue
            a=first.get(name);b=last.get(name)
            values[name]=b-a if isinstance(a,(int,float)) and isinstance(b,(int,float)) and math.isfinite(a) and math.isfinite(b) and b>=a else None
        strict[source]=values
    return dict(samples=len(samples),sample_window_s=duration,first_sample_ns=times[0],last_sample_ns=times[-1],
        gpu_time_weighted_util_pct=weighted([s.get('gpu',{}).get('gpu_util_pct') for s in samples[:-1]]),
        gpu_time_weighted_power_w=weighted([s.get('gpu',{}).get('power_w') for s in samples[:-1]]),
        vram_peak_mib=peak([s.get('gpu',{}).get('vram_used_mib') for s in samples]),process=process,
        strict_counter_deltas=strict,
        scope='Existing sampled-window observations, left-endpoint weighted, may include pre/post-request margins. Process CPU/RSS includes retained vLLM/LMCache descendants; summed RSS double-counts shared pages and omits gateway/client process memory. Missing endpoint counters stay null; source counters are not DMA time or throughput capacity.')
