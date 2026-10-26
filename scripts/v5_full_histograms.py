"""Capture native ITL histograms before/after each full run, outside its window.

Separate passive observer; never starts/resets serving or changes benchmark data.
Coverage is accepted only after clock, PID and prompt-token ledger agreement.
"""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path
import httpx
import psutil
from v5_full import build_plan
from v4_services import service_pid


def parse(text,prefix):
    counters={};buckets={}
    for line in text.splitlines():
        match=re.match(r'^([A-Za-z_:][A-Za-z0-9_:]*)(?:\{([^}]*)\})?\s+([-+0-9.eE]+)',line)
        if not match:continue
        name,labels,value=match[1],match[2] or '',float(match[3])
        if name==prefix+':inter_token_latency_seconds_bucket':
            le=re.search(r'(?:^|,)le="([^"]+)"',labels)
            if le:buckets[le[1]]=buckets.get(le[1],0)+value
        elif name in {prefix+':inter_token_latency_seconds_count',prefix+':inter_token_latency_seconds_sum',
            prefix+':prompt_tokens_total',prefix+':generation_tokens_total'}:
            counters[name]=counters.get(name,0)+value
    return dict(counters=counters,itl_cumulative_buckets=buckets)


def alive(process):
    try:return process.is_running() and process.status()!=psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:return False


def main():
    p=argparse.ArgumentParser();p.add_argument('pipeline_pid',type=int);a=p.parse_args()
    process=psutil.Process(a.pipeline_pid);assert 'scripts/v5_pipeline.py' in process.cmdline() and alive(process)
    birth=process.create_time()
    steps=[s for s in build_plan() if s['kind'] in {'sg','main'} and '-warm-' not in s['run_id']]
    assert len(steps)==17
    print('Verified full-stage observer waiting on pipeline',a.pipeline_pid,flush=True)
    for step in steps:
        rid=step['run_id'];sg=step['kind']=='sg';base=Path('results/v3/sglang' if sg else 'results/v3')
        raw=Path('results/v3/raw/sglang' if sg else 'results/v3/raw');marker=base/f'{rid}.setup.json'
        while not marker.exists():
            assert alive(process) and process.create_time()==birth,'Pipeline ended before next full run; inspect state'
            time.sleep(.2)
        assert not (raw/f'{rid}.summary.json').exists(),'Too late to establish a full baseline snapshot'
        prefix='sglang' if sg else 'vllm';url='http://127.0.0.1:8300/metrics' if sg else 'http://127.0.0.1:8000/metrics'
        service='cacheflow_v3_sglang' if sg else 'cacheflow_v2_vllm'
        def capture():
            pid=service_pid(service);start=time.monotonic_ns()
            try:
                r=httpx.get(url,timeout=5);r.raise_for_status();data=parse(r.text,prefix)
                return dict(pid=pid,start_ns=start,end_ns=time.monotonic_ns(),**data)
            except Exception as e:return dict(pid=pid,start_ns=start,end_ns=time.monotonic_ns(),error=repr(e))
        before=capture();print('Captured baseline native histogram',rid,flush=True)
        summary_path=raw/f'{rid}.summary.json'
        while not summary_path.exists():
            assert alive(process) and process.create_time()==birth,'Pipeline ended before summary'
            time.sleep(.2)
        # Summary writing may be observed mid-write; do not classify that as a
        # serving failure or restart a run. Wait only for complete JSON.
        for _ in range(50):
            try:summary=json.loads(summary_path.read_text());break
            except json.JSONDecodeError:time.sleep(.05)
        else:raise RuntimeError('summary never became complete JSON')
        after=capture();data=(raw/f'{rid}.jsonl').read_bytes();rows=[json.loads(l) for l in data.splitlines()]
        reasons=[]
        if 'error' in before or 'error' in after:reasons.append('endpoint capture failed')
        if before['pid']!=after['pid'] or before['pid']!=summary['engine_pid']:reasons.append('engine PID mismatch')
        if before['end_ns']>=min(r['scheduled_arrival_ns'] for r in rows):reasons.append('baseline capture overlaps or follows scheduled arrival')
        if after['start_ns']<=max(r['complete_ns'] for r in rows):reasons.append('final capture precedes completed responses')
        bc=before.get('counters',{});ac=after.get('counters',{})
        def delta(key):return ac[key]-bc[key] if key in ac and key in bc else None
        prompt_delta=delta(prefix+':prompt_tokens_total')
        if prompt_delta!=sum(r['input_tokens'] for r in rows):reasons.append('prompt-token window coverage mismatch')
        count=delta(prefix+':inter_token_latency_seconds_count');duration=delta(prefix+':inter_token_latency_seconds_sum')
        if count is None or duration is None or count<=0 or duration<0:reasons.append('missing or reset ITL observations')
        bd=before.get('itl_cumulative_buckets',{});ad=after.get('itl_cumulative_buckets',{})
        histogram={key:ad[key]-bd[key] for key in bd.keys()&ad.keys()}
        if any(v<0 for v in histogram.values()):reasons.append('ITL bucket counter reset')
        if histogram.get('+Inf')!=count:reasons.append('ITL histogram coverage differs from count')
        result=dict(run_id=rid,observer='Two passive GETs only; accept only before first scheduled arrival and after final completion',
            before=before,after=after,coverage_valid=not reasons,coverage_failures=reasons,
            prompt_tokens_delta=prompt_delta,itl_observations=count,
            native_itl_mean_ms=duration/count*1000 if not reasons else None,
            native_itl_cumulative_bucket_deltas=histogram if not reasons else None,
            request_file_sha256=hashlib.sha256(data).hexdigest(),
            limitations='Native per-token observation distribution, not per-request TPOT. Buckets provide quantile bounds, not exact p95. No GPU timeline or profiler is enabled.')
        out=base/f'{rid}.itl_histogram.json';out.write_text(json.dumps(result,indent=2)+'\n')
        print('Native ITL snapshot verified',rid,result['coverage_valid'],reasons,flush=True)


if __name__=='__main__':main()
