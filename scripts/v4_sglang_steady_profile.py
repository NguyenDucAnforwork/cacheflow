"""Closed-loop CPU-hot diagnostic: off/GPU-only-profiler/off, excluded from QA claims."""
import argparse
import hashlib
import re
import json
import statistics
import subprocess
import time
from pathlib import Path
import httpx
import numpy as np
from cacheflow.v2_replay import load_trace
from v3_sglang_bench import parse_metrics
from v3_sglang_runtime import load as load_runtime


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--io-backend',choices=['direct','kernel'],default='direct')
    parser.add_argument('--run-id',default='sglang_gpu_steady');args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9._-]+',args.run_id)
    root=Path('results/v3/raw')/args.run_id;root.mkdir(parents=True,exist_ok=False)
    trace=Path('data/processed/v3/v4-dev4b3-qps4-s101.jsonl')
    rows=load_trace(trace);warm=rows[:3];sequence=rows[3:15]
    assert len({r.sample_id for r in warm})==3 and len(sequence)==12
    runtime=load_runtime();assert runtime['gpu_kv_gib']==6 and runtime['host_kv_gib']==16
    assert runtime['profile_transfers'] and runtime['same_batch_guard']
    pid=int(subprocess.check_output(['supervisorctl','pid','cacheflow_v3_sglang'],text=True));assert pid>0
    records=[]
    with httpx.Client(base_url='http://127.0.0.1:8300',timeout=120) as client:
        client.get('/health').raise_for_status();info=client.get('/server_info').json()
        assert info['max_total_tokens']==43680 and info['hicache_size']==16
        assert info['hicache_io_backend']==args.io_backend and info['max_running_requests']==16
        def generate(row,phase):
            start=time.monotonic_ns();first=None;parts=[];usage=None
            body=dict(model=info['served_model_name'],prompt=row.prompt,max_tokens=4,temperature=0,
                add_special_tokens=False,stream=True,stream_options={'include_usage':True})
            with client.stream('POST','/v1/completions',json=body) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith('data: ') or line=='data: [DONE]':continue
                    value=json.loads(line[6:])
                    if value.get('usage'):usage=value['usage']
                    for choice in value.get('choices',[]):
                        part=choice.get('text') or choice.get('delta',{}).get('content')
                        if part:
                            if first is None:first=time.monotonic_ns()
                            parts.append(part)
            end=time.monotonic_ns();assert first is not None and usage
            assert usage['prompt_tokens']==row.input_tokens and 0<usage['completion_tokens']<=4
            text=''.join(parts)
            record=dict(phase=phase,request_id=row.request_id,sample_id=row.sample_id,input_tokens=row.input_tokens,
                output_tokens=usage['completion_tokens'],start_ns=start,first_token_ns=first,end_ns=end,
                ttft_ms=(first-start)/1e6,latency_ms=(end-start)/1e6,output=text,
                output_hash=hashlib.sha256(text.encode()).hexdigest())
            records.append(record);return record
        # Prime code/JIT paths, then discard all KV state before every measured phase.
        client.post('/flush_cache',params={'timeout':10}).raise_for_status()
        for row in [*warm,*sequence]:generate(row,'primer')
        phases=[]
        for phase,profiled in [('off_before',False),('gpu_profile',True),('off_after',False)]:
            client.post('/flush_cache',params={'timeout':10}).raise_for_status()
            for row in warm:generate(row,phase+'_warm')
            time.sleep(1) # drain asynchronous write-through uniformly, outside measurement
            before=client.get('/metrics');before.raise_for_status();before=parse_metrics(before.text)
            payload=dict(output_dir=str(root.resolve()),activities=['GPU'],with_stack=False,
                record_shapes=False,profile_by_stage=False,profile_prefix='steady-cpu-hot')
            if profiled:client.post('/start_profile',json=payload).raise_for_status()
            start=time.monotonic_ns();measured=[generate(row,phase) for row in sequence];end=time.monotonic_ns()
            if profiled:client.post('/stop_profile').raise_for_status()
            after=client.get('/metrics');after.raise_for_status();after=parse_metrics(after.text)
            def delta(key):return after[key]-before.get(key,0) if key in after else None
            assert delta('sglang:prompt_tokens_total')==sum(r.input_tokens for r in sequence)
            assert delta('sglang:load_back_tokens_total')>0,'CPU-hot restore opportunity missing'
            phases.append(dict(phase=phase,profiled=profiled,start_ns=start,end_ns=end,requests=12,
                ttft_p50_ms=float(np.percentile([r['ttft_ms'] for r in measured],50)),
                ttft_p95_ms=float(np.percentile([r['ttft_ms'] for r in measured],95)),
                wall_s=(end-start)/1e9,host_promoted_tokens=delta('sglang:load_back_tokens_total'),
                uncached_tokens=delta('sglang:uncached_prompt_tokens_histogram_sum'),
                profile_payload=payload if profiled else None))
    assert pid==int(subprocess.check_output(['supervisorctl','pid','cacheflow_v3_sglang'],text=True))
    (root/'requests.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in records))
    source_names=['scripts/v4_sglang_steady_profile.py','scripts/sglang_profile_hooks/sitecustomize.py',
        'src/cacheflow/v3_sglang_transfer_profile.py','src/cacheflow/v4_sglang_admission_profile.py',
        'src/cacheflow/v4_sglang_delayhit.py']
    off=[r for r in phases if not r['profiled']];on=next(r for r in phases if r['profiled'])
    result=dict(scope='CPU-hot closed-loop diagnostic,4 output tokens,12 requests/phase; not main performance or QA evaluation',
        runtime=runtime,engine_pid=pid,server_config={key:info.get(key) for key in
            ['model_path','served_model_name','max_total_tokens','hicache_size','hicache_io_backend',
             'hicache_mem_layout','schedule_policy','attention_backend','max_running_requests',
             'chunked_prefill_size','cuda_graph_config','version']},phases=phases,
        profiler_p95_delta_vs_off_mean_pct=100*(on['ttft_p95_ms']/statistics.mean(r['ttft_p95_ms'] for r in off)-1),
        trace_source_sha256=hashlib.sha256(trace.read_bytes()).hexdigest(),
        source_sha256={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in source_names},
        cuda_traces=[str(p) for p in root.glob('*.trace.json.gz')])
    assert result['cuda_traces'],'native profiler produced no trace'
    target=Path('results/v3/sglang/v4_steady_profile_setup.json') if args.run_id=='sglang_gpu_steady' else Path(f'results/v3/sglang/{args.run_id}.setup.json')
    assert not target.exists(),'diagnostic result already exists'
    target.write_text(json.dumps(result,indent=2)+'\n')
    for phase in phases:print(phase)


if __name__=='__main__':main()
