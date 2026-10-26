"""Missing-aware native resource summaries from existing retained samples only."""
from v4_analyze_sglang_resources import analyze as original


def analyze(samples):
    result=original(samples)
    retract=[s['sglang'].get('sglang:num_retracted_reqs') for s in samples]
    queue=[s['sglang'].get('sglang:num_queue_reqs') for s in samples]
    result['retract_gauge_samples_observed']=sum(v is not None for v in retract)
    result['retract_gauge_peak']=max(retract) if all(v is not None for v in retract) else None
    result['queue_samples_observed']=sum(v is not None for v in queue)
    if any(v is None for v in queue):
        result['sampled_queue_above128_s']=None;result['sampled_queue_above128_fraction']=None
    result['scope']='Existing1Hz sample-window estimates, left-endpoint weighted; may include pre/post-request margins. Missing endpoint counters/gauge coverage stay null; RSS sums double-count shared pages. Host promotions/enqueue duration are not engine-consumed-source tokens, measured DMA time or useful latency overlap. Queue>128 samples identify a fallback condition, not exact scheduler decisions.'
    return result
