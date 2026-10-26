"""Preserve a live incomplete run's stalled counters; never emit latency claims."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import httpx
import psutil


def main():
    p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument('--engine-pid',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path('results/v3/raw');path=root/f'{a.run_id}.metrics.jsonl'
    blob=path.read_bytes();lines=blob.splitlines();samples=[]
    for i,line in enumerate(lines):
        try:samples.append(json.loads(line))
        except json.JSONDecodeError:
            assert i==len(lines)-1, 'Only an incomplete final append may be ignored'
    assert samples and not (root/f'{a.run_id}.summary.json').exists(), 'This audit describes a live unfinished run only'
    progress=['vllm:prompt_tokens_total','vllm:request_prefill_kv_computed_tokens_sum',
              'vllm:prompt_tokens_source_external_kv_transfer_total','vllm:time_to_first_token_seconds_count']
    def state(s):
        m=s['vllm'];return tuple(m.get(k) for k in progress)
    def stalled(s):
        m=s['vllm'];return m.get('vllm:num_requests_running')==0 and m.get('vllm:num_requests_waiting',0)>0 and m.get('vllm:kv_cache_usage_perc',0)>.99 and s['gpu'].get('gpu_util_pct')==0
    suffix=[];last=state(samples[-1]);assert all(x is not None for x in last)
    for s in reversed(samples):
        if not stalled(s) or state(s)!=last:break
        suffix.append(s)
    suffix.reverse();assert len(suffix)>=2
    engine=psutil.Process(a.engine_pid);assert engine.is_running() and 'vllm' in ' '.join(engine.cmdline())
    with httpx.Client(timeout=5) as c:health=c.get('http://127.0.0.1:8100/health');health.raise_for_status();health=health.json()
    global_log=Path('results/v3/raw/gateway.jsonl')
    completed=[r for r in map(json.loads,global_log.read_text().splitlines()) if r.get('run_id')==a.run_id]
    result=dict(run_id=a.run_id,status='live incomplete stalled observation; no terminal failure or latency inference',
        observed_monotonic_ns=time.monotonic_ns(),engine_pid=engine.pid,engine_created_unix_s=engine.create_time(),
        sampled_no_progress_s=(suffix[-1]['timestamp_ns']-suffix[0]['timestamp_ns'])/1e9,
        samples_in_contiguous_suffix=len(suffix),first=suffix[0],last=suffix[-1],progress_keys=progress,
        gateway_health=health,gateway_completed_records=len(completed),
        gateway_completed_request_ids=[r['request_id'] for r in completed],
        metric_file_sha256_at_observation=hashlib.sha256(blob).hexdigest(),
        limitations='Counters, occupancy and zero sampled GPU utilization do not expose internal request states, free-block references or pending connector futures. Root cause is unproven. No retry/reset/profiler was used; the request timeout remains unchanged.')
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print('Observed stalled suffix',result['sampled_no_progress_s'],'seconds;',len(completed),'gateway completions;',health['active'],'active;',health['queue'],'queued')


if __name__=='__main__':main()
