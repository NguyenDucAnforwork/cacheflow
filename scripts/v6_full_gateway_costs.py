"""Hash-bound chooser CPU counters from completed full-arm setup snapshots."""
import argparse
import json
import math
from pathlib import Path
from v5_verify import verify
from v6_raw_archive import sha


def analyze(checkpoint,output):
    checkpoint=Path(checkpoint);output=Path(output);assert not output.exists()
    report=json.loads(checkpoint.read_text());assert report['kind']=='interim_full_checkpoint_not_terminal_audit'
    parent,seal=verify();source='src/cacheflow/v3_memory_scheduler.py';assert sha(source)==parent['source_sha256'][source]
    rows=[]
    for run in report['runs']:
        if run['step']['engine']!='main':continue
        rid=run['run_id'];ap=Path(f'results/v3/{rid}.full_audit_r1.json');sp=Path(f'results/v3/{rid}.setup.json')
        assert sha(ap)==run['audit_sha256'];audit=json.loads(ap.read_text());assert sha(sp)==audit['setup_sha256']
        setup=json.loads(sp.read_text());assert setup['source_files_sha256'][source]==sha(source)
        before=setup['gateway_before'].get('decision_stats');after=setup['gateway_after'].get('decision_stats')
        if after is None:
            assert before is None;stats=None
        else:
            assert before is not None and before['calls']==before['cache_hits']==before['cpu_ms']==before['wall_ms']==0
            calls=after['calls'];hits=after['cache_hits']
            assert all(isinstance(n,int) and not isinstance(n,bool) for n in [calls,hits]) and 0<=hits<=calls and calls>0
            assert all(isinstance(after[k],(int,float)) and math.isfinite(after[k]) and after[k]>=0 for k in ['cpu_ms','wall_ms','max_ms'])
            stats=dict(calls=calls,cache_hits=hits,cache_misses=calls-hits,cache_hit_fraction=hits/calls,
                thread_cpu_s=after['cpu_ms']/1000,wall_s=after['wall_ms']/1000,max_call_wall_ms=after['max_ms'],
                mean_thread_cpu_us_per_call=after['cpu_ms']*1000/calls,
                thread_cpu_s_per_request=after['cpu_ms']/1000/1986,
                thread_cpu_s_divided_by_run_wall_s=(after['cpu_ms']/1000)/run['summary']['duration_s'])
        rows.append(dict(run_id=rid,arm=run['step']['arm'],seed=run['step']['seed'],requests=1986,
            setup_sha256=sha(sp),audit_sha256=sha(ap),decision_stats=stats))
    result=dict(checkpoint_sha256=sha(checkpoint),source_sha256=sha(__file__),chooser_implementation_sha256=sha(source),runs=rows,
        scope='Instrumented chooser thread CPU/wall only, including cache-key construction, cache hits and misses; excludes next-timeout/condition handling, tokenization, HTTP and other gateway work. Max is call wall, not call CPU. Missing FIFO/bundle counters remain null, not0. CPU/run-wall ratio is a one-thread-equivalent descriptor, not causal blocked-wall fraction, total gateway CPU, energy or measured latency saved by a future optimization. No hit-versus-miss CPU split was captured.')
    with output.open('x') as out:out.write(json.dumps(result,indent=2)+'\n')
    print('Chooser counters checked',len(rows),'full arms',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('checkpoint',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();analyze(a.checkpoint,a.output)
