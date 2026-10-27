import sys as _namespace_sys
from pathlib import Path as _NamespacePath
_namespace_sys.path.insert(1, str(_NamespacePath(__file__).resolve().parents[2]))
"""Read-only candidate-inclusive full study plan; execution requires a later freeze.

All current primary and ablation methods remain in the full matrix. Development
results cannot silently remove the less favorable policy after full scores exist.
"""
import json


def build_plan():
    steps=[]
    main={'fifo64':('fifo',64),'bundle16':('bundle_wave',16),'union64':('packing_reuse',64),'packing_ready':('packing_ready',64)}
    native={'native_lpm':('lpm',None),'native_dfs':('dfs-weight',None),'fifo64':('lpm','fifo'),
        'union64':('lpm','packing_reuse'),'packing_ready':('lpm','packing_ready')}
    for seed in [901,902,903]:
        for engine,arms in [('main',main),('sg',native)]:
            order=list(arms)
            if seed==902:order.reverse()
            elif seed==903:order=order[2:]+order[:2]
            for arm in order:
                policy,cap=arms[arm] if engine=='main' else (arms[arm][1],64)
                steps.append(dict(engine=engine,arm=arm,policy=policy,cap=cap,queue=512,budget=6,host_flag=48,
                    native_policy=arms[arm][0] if engine=='sg' else None,seed=seed,requests=1986,
                    trace=f'data/processed/v3/v5-full4b-qps4-s{seed}.jsonl.gz',
                    run_id=f'v6repro_r1_reference-{engine}-g6-{arm}-s{seed}'))
    for arm in ['native_lpm','union64','packing_ready']:
        steps.append(dict(engine='sg',arm=arm,policy=native[arm][1],cap=64,queue=512,budget=10,host_flag=48,
            native_policy='lpm',seed=901,requests=1986,trace='data/processed/v3/v5-full4b-qps4-s901.jsonl.gz',
            run_id=f'v6repro_r1_reference-sg-g10-{arm}-s901'))
    return steps


if __name__=='__main__':
    steps=build_plan()
    print(json.dumps(dict(status='Prepared/unrun; not a final-method freeze or authorization to launch concurrent engines',
        scope='30full arms59580scheduled requests, same1986QA at3arrival schedules plus single-seed larger-cache control. '
              'Fresh engine per arm with60separate warmup requests each. All previously exposed semantic data; not a fresh holdout.',
        actions=steps),indent=2))
