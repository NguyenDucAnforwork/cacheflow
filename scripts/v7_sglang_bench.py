"""Run an upstream SGLang/HiCache arm with native metrics and captured QA outputs."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psutil

from cacheflow.collect_metrics import gpu_snapshot
from v3_sglang_runtime import load as load_runtime
from v3_model import get_model
from v2_extract_gateway import extract as extract_gateway
from v6_native_metrics import capture as capture_native,summarize as summarize_native
from v7_gateway_identity import capture as capture_gateway_identity,validate_replay_window as validate_gateway_pair


def parse_metrics(text):
    values={}
    for line in text.splitlines():
        match=re.match(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{.*\})?\s+([-+0-9.eE]+)',line)
        if match and not match[1].endswith('_bucket'):
            values[match[1]]=values.get(match[1],0)+float(match[2])
    return values


def main():
    p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument('trace',type=Path)
    p.add_argument('--url',default='http://127.0.0.1:8300')
    p.add_argument('--replay-url');p.add_argument('--gateway-policy');p.add_argument('--warmup',action='store_true');p.add_argument('--scheduler-implementation',choices=['reference','epoch']);args=p.parse_args()
    replay_url=args.replay_url or args.url
    assert bool(args.gateway_policy)==bool(args.replay_url), 'gateway mode requires replay URL and policy together'
    assert bool(args.scheduler_implementation)==bool(args.gateway_policy),'Explicit implementation is required exactly for gateway arms'
    assert re.fullmatch(r'[A-Za-z0-9._-]+',args.run_id)
    base=Path('results/v3/sglang');raw=Path('results/v3/raw/sglang')
    base.mkdir(parents=True,exist_ok=True);raw.mkdir(parents=True,exist_ok=True)
    setup=base/f'{args.run_id}.setup.json'
    if setup.exists():raise FileExistsError('run ID already exists: '+args.run_id)
    gateway_reset=None
    if args.gateway_policy:
        with httpx.Client(timeout=10) as client:
            previous=client.get(replay_url+'/health').json()
        assert previous['active']==previous['queue']==0,'refusing to restart a busy gateway'
        subprocess.run(['supervisorctl','restart','cacheflow_v2_gateway'],check=True)
        for _ in range(120):
            try:
                with httpx.Client(timeout=2) as client:
                    state=client.get(replay_url+'/health');state.raise_for_status()
                break
            except (httpx.HTTPError,ValueError):time.sleep(.5)
        else:raise RuntimeError('gateway reset readiness timeout')
        gateway_reset=dict(method='supervisor_restart',previous_decision_stats=previous.get('decision_stats'))
    with httpx.Client(timeout=30) as client:
        client.get(args.url+'/health').raise_for_status()
        # Flush rejects outstanding requests; do not hide a failed reset.
        time.sleep(2)
        reset=client.post(args.url+'/flush_cache',params={'timeout':10});reset.raise_for_status()
        info=client.get(args.url+'/server_info').json()
        gateway_before=client.get(replay_url+'/health').json() if args.gateway_policy else None
        if gateway_before:
            assert gateway_before['active']==gateway_before['queue']==0
            assert gateway_before['policy']==args.gateway_policy
            assert gateway_before['completed_history_requests']==0,'gateway prefix history was not reset'
            if gateway_before.get('decision_stats'):
                assert gateway_before['decision_stats']['calls']==0,'gateway scheduler state was not reset'
    runtime=load_runtime();model=get_model(runtime['model_key'])
    gpu_bytes=runtime['gpu_kv_gib']*1024**3
    assert info['max_total_tokens']==gpu_bytes//(16*model['bytes_per_token'])*16
    assert info['enable_hierarchical_cache'] and info['hicache_size']==runtime['host_kv_gib']
    assert info['model_path']==model['path']
    assert info['schedule_policy']==runtime['schedule_policy']
    assert info['hicache_io_backend']==runtime['io_backend']
    assert info['attention_backend']==runtime['attention_backend']
    assert info['max_running_requests']==runtime['max_running_requests']
    launcher=int(subprocess.check_output(['supervisorctl','pid','cacheflow_v3_sglang'],text=True))
    assert launcher>0
    children=[psutil.Process(launcher),*psutil.Process(launcher).children(recursive=True)]
    servers=[x for x in children if 'sglang.launch_server' in x.cmdline()]
    assert len(servers)==1, 'expected one native Python launcher'
    env=servers[0].environ()
    public_env={key:env.get(key) for key in [
        'IN_BATCH_PREFIX_CACHING_CHECK_THRESHOLD',
        'IN_BATCH_PREFIX_CACHING_DEPRIORITIZE_THRESHOLD',
        'CACHEFLOW_SGLANG_TRANSFER_PROFILE','CACHEFLOW_SG_SAME_BATCH_GUARD']}
    assert public_env['IN_BATCH_PREFIX_CACHING_CHECK_THRESHOLD']==str(runtime['inbatch_check_threshold'])
    assert public_env['IN_BATCH_PREFIX_CACHING_DEPRIORITIZE_THRESHOLD']==str(runtime['inbatch_deprioritize_threshold'])
    assert (public_env['CACHEFLOW_SGLANG_TRANSFER_PROFILE']=='1')==runtime['profile_transfers']
    assert (public_env['CACHEFLOW_SG_SAME_BATCH_GUARD']=='1')==runtime['same_batch_guard']
    allow=['model_path','served_model_name','dtype','context_length','max_total_tokens',
        'max_running_requests','chunked_prefill_size','page_size','mem_fraction_static',
        'enable_hierarchical_cache','hicache_size','hicache_write_policy','hicache_io_backend',
        'hicache_mem_layout','schedule_policy','attention_backend','disable_cuda_graph',
        'disable_decode_cuda_graph','disable_prefill_cuda_graph','cuda_graph_config','version']
    c=dict(run_id=args.run_id,warmup=args.warmup,engine_kind='sglang',cache_backend='upstream_hicache',
        source_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        runtime=runtime, model=model, nominal_gpu_kv_bytes=gpu_bytes,
        replay_url=replay_url,gateway_policy=args.gateway_policy,gateway_before=gateway_before,gateway_reset=gateway_reset,
        gateway_config=Path('.cacheflow-v3-gateway.yaml').read_text() if args.gateway_policy else None,
        server_config={k:info.get(k) for k in allow},launcher_pid=launcher,
        process_argv={str(x.pid):x.cmdline() for x in children},public_server_env=public_env,reset_status=reset.status_code,
        captured_utc=datetime.now(timezone.utc).isoformat())
    c['package_versions']={name:importlib.metadata.version(name) for name in
        ['sglang','sglang-kernel','torch','transformers','flashinfer-python','flashinfer-cubin']}
    import sglang
    source_root=Path(sglang.__file__).parent
    source_names=['srt/managers/schedule_policy.py','srt/managers/cache_controller.py',
                  'srt/mem_cache/hiradix_cache.py','srt/mem_cache/memory_pool_host.py']
    c['upstream_source_sha256']={name:hashlib.sha256((source_root/name).read_bytes()).hexdigest()
                                 for name in source_names}
    c['frontend_source_sha256']={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in
        ['scripts/v3_sglang_bench.py','src/cacheflow/v2_replay.py','src/cacheflow/collect_metrics.py',
         'scripts/v6_sglang_bench.py','src/cacheflow/v6_replay.py','scripts/v6_native_metrics.py','scripts/v5_full_histograms.py']}
    if runtime['profile_transfers']:
        c['profiler_source_sha256']={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in
            ['scripts/sglang_profile_hooks/sitecustomize.py','src/cacheflow/v3_sglang_transfer_profile.py',
             'src/cacheflow/v4_sglang_admission_profile.py']}
    if runtime['same_batch_guard']:
        c['native_component_adaptation']='same-batch delay-hit guard only; not full Strata'
        c['native_overlay_source_sha256']={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in
            ['scripts/sglang_profile_hooks/sitecustomize.py','src/cacheflow/v4_sglang_delayhit.py']}
    c['v6_source_sha256']={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in
        ['src/cacheflow/v6_gateway.py','src/cacheflow/v6_ready_scheduler.py','scripts/v6_runtime.py','scripts/v6_serve_gateway.sh']}
    c['v7_source_sha256']={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in
        ['scripts/v7_sglang_bench.py','scripts/v7_gateway_identity.py','src/cacheflow/v7_gateway.py','src/cacheflow/v7_epoch_scheduler.py','scripts/v7_serve_gateway.sh']}
    if args.gateway_policy:
        gateway_pid=int(subprocess.check_output(['supervisorctl','pid','cacheflow_v2_gateway'],text=True))
        gateway_argv=psutil.Process(gateway_pid).cmdline();assert 'cacheflow.v7_gateway:create_app' in gateway_argv
        c['gateway_runtime_entrypoint']=dict(pid=gateway_pid,argv=gateway_argv)
        c['gateway_implementation_before']=capture_gateway_identity(replay_url,args.gateway_policy,args.scheduler_implementation,require_fresh=True)
        names=['src/cacheflow/gateway.py','src/cacheflow/v3_memory_scheduler.py',
               'src/cacheflow/scheduler.py','src/cacheflow/prefix.py','src/cacheflow/v4_prepare.py']
        c['gateway_source_sha256']={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in names}
    setup.write_text(json.dumps(c,indent=2)+'\n')
    stop=threading.Event();samples=[];collector_error=[]
    def sample():
        try:
            with httpx.Client(timeout=5) as client, (raw/f'{args.run_id}.metrics.jsonl').open('w') as f:
                while True:
                    response=client.get(args.url+'/metrics');response.raise_for_status()
                    processes=[psutil.Process(launcher),*psutil.Process(launcher).children(recursive=True)]
                    rss=0;live_count=0
                    for member in processes:
                        try:
                            rss+=member.memory_info().rss;live_count+=1
                        except (psutil.NoSuchProcess,psutil.AccessDenied):
                            continue
                    row=dict(timestamp_ns=time.monotonic_ns(),sglang=parse_metrics(response.text),
                        gpu=gpu_snapshot(),processes=live_count,summed_process_rss_bytes=rss)
                    samples.append(row);f.write(json.dumps(row,sort_keys=True)+'\n');f.flush()
                    if stop.wait(1):break
        except Exception as e:collector_error.append(repr(e))
    native_before=capture_native(args.url+'/metrics','sglang','cacheflow_v3_sglang')
    thread=threading.Thread(target=sample);thread.start()
    try:
        cmd=[sys.executable,'-m','cacheflow.v6_replay','--trace',str(args.trace),'--url',replay_url,
            '--run-id',args.run_id,'--output',str(raw/f'{args.run_id}.jsonl'),
            '--registry',str(base/'registry.csv'),'--capture-text','--engine-kind','sglang',
            '--engine-pid',str(launcher),'--model-revision',Path(info['model_path']).name,
            '--model-name',info['served_model_name'],'--mode','SG',
            '--policy',args.gateway_policy or 'sglang_'+info['schedule_policy'],'--gpu-kv-bytes',str(gpu_bytes)]
        subprocess.run(cmd,check=True,env=os.environ.copy())
        native_after=capture_native(args.url+'/metrics','sglang','cacheflow_v3_sglang')
        time.sleep(2)
    finally:
        stop.set();thread.join(timeout=15)
    assert not collector_error and not thread.is_alive(),collector_error
    assert len(samples)>=2
    assert launcher==int(subprocess.check_output(['supervisorctl','pid','cacheflow_v3_sglang'],text=True))
    requests=[json.loads(line) for line in (raw/f'{args.run_id}.jsonl').read_text().splitlines()]
    assert all(x['status']=='ok' and x['server_prompt_tokens']==x['input_tokens'] for x in requests)
    counter_names=set(samples[0]['sglang'])|set(samples[-1]['sglang'])
    deltas={name:(samples[-1]['sglang'][name]-samples[0]['sglang'][name]
        if name in samples[-1]['sglang'] and name in samples[0]['sglang'] else None) for name in sorted(counter_names)
        if name.startswith('sglang:') and name.endswith(('_total','_sum','_count'))}
    (base/f'{args.run_id}.metrics_summary.json').write_text(json.dumps(dict(
        counter_deltas=deltas,samples=len(samples),
        first_counter_endpoints={k:samples[0]['sglang'].get(k) for k in deltas},
        last_counter_endpoints={k:samples[-1]['sglang'].get(k) for k in deltas},scope='native source labels; load_back tokens are not vLLM engine-consumed-source tokens'),indent=2)+'\n')
    total=sum(x['input_tokens'] for x in requests)
    assert deltas['sglang:prompt_tokens_total']==total
    if not args.warmup or all(deltas.get(k) is not None for k in ['sglang:cached_tokens_total','sglang:uncached_prompt_tokens_histogram_sum']):
        assert deltas['sglang:cached_tokens_total']+deltas['sglang:uncached_prompt_tokens_histogram_sum']==total
    summary=json.loads((raw/f'{args.run_id}.summary.json').read_text())
    native=summarize_native(args.run_id,native_before,native_after,requests,summary,'sglang')
    native['request_file_sha256']=hashlib.sha256((raw/f'{args.run_id}.jsonl').read_bytes()).hexdigest()
    (base/f'{args.run_id}.itl_histogram.json').write_text(json.dumps(native,indent=2)+'\n')
    if args.gateway_policy:
        extract_gateway(Path('results/v3/raw/gateway.jsonl'),raw/f'{args.run_id}.jsonl',
                        args.run_id,raw/f'{args.run_id}.gateway.jsonl')
        with httpx.Client(timeout=10) as client:after=client.get(replay_url+'/health').json()
        assert after['active']==after['queue']==0
        c['gateway_after']=after
        c['gateway_implementation_after']=capture_gateway_identity(replay_url,args.gateway_policy,args.scheduler_implementation)
        validate_gateway_pair(c['gateway_implementation_before'],c['gateway_implementation_after'],requests)
        setup.write_text(json.dumps(c,indent=2)+'\n')
    print('Verified SGLang replay',args.run_id,flush=True)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        if not isinstance(exc,FileExistsError) and len(sys.argv)>1 and re.fullmatch(r'[A-Za-z0-9._-]+',sys.argv[1]):
            path=Path('results/v3/sglang')/(sys.argv[1]+'.invalid');path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('Run failed integrity/replay checks: '+repr(exc)+'\n')
        raise
