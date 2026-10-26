"""Native histogram boundary snapshots; no profiler, reset or parameter changes."""
import time
import math
import httpx
from v4_services import service_pid
from v5_full_histograms import parse


def capture(url,prefix,service):
    pid=service_pid(service);start=time.monotonic_ns()
    try:
        r=httpx.get(url,timeout=5);r.raise_for_status()
        return dict(pid=pid,start_ns=start,end_ns=time.monotonic_ns(),**parse(r.text,prefix))
    except Exception as exc:return dict(pid=pid,start_ns=start,end_ns=time.monotonic_ns(),error=repr(exc))


def summarize(rid,before,after,rows,summary,prefix):
    reasons=[]
    if 'error' in before or 'error' in after:reasons.append('Native endpoint capture failed')
    if not rows:
        return dict(run_id=rid,coverage_valid=False,coverage_failures=['Empty client ledger'],native_itl_mean_ms=None,native_itl_cumulative_bucket_deltas=None)
    if before['pid']<=0 or before['pid']!=after['pid'] or before['pid']!=summary['engine_pid']:reasons.append('Engine PID mismatch')
    if before['end_ns']>=min(r['scheduled_arrival_ns'] for r in rows):reasons.append('Baseline is not before first scheduled arrival')
    if after['start_ns']<=max(r['complete_ns'] for r in rows):reasons.append('Final capture is not after response completion')
    bc=before.get('counters',{});ac=after.get('counters',{})
    def delta(key):return ac[key]-bc[key] if key in bc and key in ac else None
    prompt=delta(prefix+':prompt_tokens_total');generation=delta(prefix+':generation_tokens_total')
    if prompt!=sum(r['input_tokens'] for r in rows):reasons.append('Prompt-token coverage mismatch')
    if any(r['status']!='ok' or r['output_tokens'] is None for r in rows):reasons.append('Incomplete client generation ledger')
    elif generation!=sum(r['output_tokens'] for r in rows):reasons.append('Generation-token coverage mismatch')
    count=delta(prefix+':inter_token_latency_seconds_count');duration=delta(prefix+':inter_token_latency_seconds_sum')
    if count is None or duration is None or count<=0 or duration<0:reasons.append('Missing/reset ITL observations')
    bd=before.get('itl_cumulative_buckets',{});ad=after.get('itl_cumulative_buckets',{})
    histogram={k:ad[k]-bd[k] for k in bd.keys()&ad.keys()}
    if set(bd)!=set(ad) or not bd:reasons.append('Bucket schema missing/changed')
    ordered=sorted(histogram,key=float)
    if (any(not math.isfinite(v) or v<0 for v in histogram.values())
        or histogram.get('+Inf')!=count
        or any(histogram[a]>histogram[b] for a,b in zip(ordered,ordered[1:]))):
        reasons.append('Bucket coverage/reset/monotonicity mismatch')
    if any(v is not None and not math.isfinite(v) for v in [count,duration,prompt,generation]):reasons.append('Nonfinite native counters')
    return dict(run_id=rid,before=before,after=after,coverage_valid=not reasons,coverage_failures=reasons,
        prompt_tokens_delta=prompt,generation_tokens_delta=generation,itl_observations=count,
        native_itl_mean_ms=duration/count*1000 if not reasons else None,
        native_itl_cumulative_bucket_deltas=histogram if not reasons else None,
        limitations='Native engine histogram semantics, not exact client individual-token timestamps. SG weights averaged update intervals by new-token count; vLLM observes engine-output update intervals. Bucket quantiles are bounds. No GPU profiler enabled.')
