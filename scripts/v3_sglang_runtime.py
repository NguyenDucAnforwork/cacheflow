"""Explicit, reproducible upstream HiCache baseline settings; independent of vLLM marker."""
import argparse
import json
from pathlib import Path

from v3_model import MODELS, get_model

ROOT=Path(__file__).resolve().parents[1]
MARKER=ROOT/'.cacheflow-sglang-runtime.json'
DEFAULT=dict(model_key='qwen3-1.7b',gpu_kv_gib=4,max_running_requests=16,
    batch_tokens=8192,io_backend='kernel',attention_backend='triton',schedule_policy='lpm',graphs=True,
    profile_transfers=False)


def load():
    return DEFAULT | (json.loads(MARKER.read_text()) if MARKER.exists() else {})


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['configure','args','validate'])
    p.add_argument('--model',choices=list(MODELS),default=DEFAULT['model_key'])
    p.add_argument('--gpu-kv-gib',type=int,choices=[4,6,8,10],default=4)
    p.add_argument('--max-running-requests',type=int,default=16)
    p.add_argument('--batch-tokens',type=int,default=8192)
    p.add_argument('--io-backend',choices=['kernel','direct'],default='kernel')
    p.add_argument('--attention-backend',choices=['triton','flashinfer'],default='triton')
    p.add_argument('--schedule-policy',choices=['lpm','fcfs','dfs-weight'],default='lpm')
    p.add_argument('--profile-transfers',action='store_true')
    p.add_argument('--no-graphs',action='store_true');a=p.parse_args()
    if a.command=='configure':
        c=dict(model_key=a.model,gpu_kv_gib=a.gpu_kv_gib,max_running_requests=a.max_running_requests,
            batch_tokens=a.batch_tokens,io_backend=a.io_backend,attention_backend=a.attention_backend,
            schedule_policy=a.schedule_policy,graphs=not a.no_graphs,profile_transfers=a.profile_transfers)
        MARKER.write_text(json.dumps(c,indent=2)+'\n')
    c=load();model=get_model(c['model_key'])
    tokens=c['gpu_kv_gib']*1024**3//(16*model['bytes_per_token'])*16
    assert tokens>=32768,'KV budget cannot hold the configured 32K maximum context'
    assert 1<=c['max_running_requests']<=32 and c['batch_tokens']>=2048
    if model['adoption']:
        audit=json.loads((ROOT/model['adoption']).read_text())
        assert audit['revision']==model['revision'] and audit['repo']==model['repo']
        assert all((Path(model['path'])/x['file']).stat().st_size==x['size'] for x in audit['weights'])
    if a.command=='args':
        args=['--model-path',model['path'],'--served-model-name',model['served_name'],
            '--host','127.0.0.1','--port','8300','--dtype','bfloat16','--context-length','32768',
            '--max-total-tokens',str(tokens),'--max-running-requests',str(c['max_running_requests']),
            '--random-seed','0','--chunked-prefill-size',str(c['batch_tokens']),'--page-size','16',
            '--mem-fraction-static','0.8','--enable-hierarchical-cache','--hicache-size','16',
            '--hicache-write-policy','write_through','--hicache-io-backend',c['io_backend'],
            '--hicache-mem-layout','page_first_direct' if c['io_backend']=='direct' else 'page_first',
            '--schedule-policy',c['schedule_policy'],'--enable-metrics','--attention-backend',c['attention_backend']]
        if not c['graphs']:args+=['--disable-decode-cuda-graph','--disable-prefill-cuda-graph']
        print('\n'.join(args))
    else:print(json.dumps(c|dict(max_total_tokens=tokens,model=model),sort_keys=True))


if __name__=='__main__':main()
