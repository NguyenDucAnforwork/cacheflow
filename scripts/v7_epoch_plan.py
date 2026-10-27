"""Read-only next development screen; no registration, freeze or GPU launch."""
import argparse
import json


def build_plan():
    rows=[]
    arms=[('main','bundle16','bundle_wave','reference',16,None),
        ('main','union64','packing_reuse','reference',64,None),
        ('main','epoch_union64','packing_reuse','epoch',64,None),
        ('sg','native_dfs',None,None,None,'dfs-weight'),
        ('sg','union64','packing_reuse','reference',64,'lpm'),
        ('sg','epoch_union64','packing_reuse','epoch',64,'lpm')]
    for seed in [101,102,103]:
        order=arms if seed==101 else list(reversed(arms)) if seed==102 else arms[3:]+arms[:3]
        for engine,arm,policy,implementation,cap,native in order:
            rows.append(dict(engine=engine,arm=arm,policy=policy,implementation=implementation,cap=cap,native_policy=native,
                seed=seed,requests=60,warmup_requests=60,gpu_kv_gib=6,host_payload_bytes=16000745472,
                max_queue=512,max_bypasses=8,max_native_sequences=16,batch_tokens=8192,timeout_s=180,keepalive_connections=0,
                trace=f'data/processed/v3/v5-dev4b3-qps4-s{seed}.jsonl',run_id=f'v7dev1-epoch-{engine}-{arm}-s{seed}'))
    return rows


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true',required=True);p.parse_args()
    print(json.dumps(dict(status='Prepared only; no GPU controller/registration/freeze or result',
        phase='Development screen, not completion of the research objective',actions=build_plan(),
        measured_requests=1080,separate_warmup_requests=1080,unique_qa=60,
        prerequisites='Complete original30-arm audit and successful from-source/namespace/CPU/real-prefix chain; idle services; new prospective registration and tested controller/auditor required before execution',
        scope='Fresh engine per arm; three balanced arrival schedules over previously exposed60QA. Main bundle and nativeDFS remain the strong references; originalunion remains the same-policy optimization baseline. No comparison with results from old processes. GPU-fit/low-reuse/load/quality controls and new full confirmation remain necessary after a promising screen.'),indent=2))
