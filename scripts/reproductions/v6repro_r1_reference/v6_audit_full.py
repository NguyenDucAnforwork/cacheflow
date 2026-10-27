import sys as _namespace_sys
from pathlib import Path as _NamespacePath
_namespace_sys.path.insert(1, str(_NamespacePath(__file__).resolve().parents[2]))
"""Reopen and verify all full raw archives, then build matched full-study evidence."""
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from v6_freeze_full import verify_full,PATH,sha
from v6_raw_archive import expanded
from v6_full_contracts import audit_configuration
from v3_analyze_runs import load
from v4_audit_sglang_runs import audit as native_integrity
from v5_run_intervals import paired_log_interval


def read(path):return json.loads(Path(path).read_text())


def fresh_process_units(runs):
    """Verify the registered 12 main / 18 native process units independently."""
    assert len(runs)==30 and all(r['engine'] in {'main','sg'} for r in runs)
    engines=[r['engine_pid'] for r in runs]
    caches=[r['lmcache_pid'] for r in runs if r['engine']=='main']
    assert len(caches)==12
    for name,pids,count in [('engine',engines,30),('lmcache',caches,12)]:
        assert all(isinstance(pid,int) and not isinstance(pid,bool) and pid>0 for pid in pids),(name,'Missing/invalid process identity')
        assert len(set(pids))==count,(name,'Process retained across full arms')
    assert all(r['lmcache_pid'] is None for r in runs if r['engine']=='sg')
    return dict(distinct_engine_pids=30,distinct_main_lmcache_pids=12,
        scope='Captured supervisor PID units; warm/measured identity is checked per arm. Unique numeric PIDs are not a proof of native liveness or stable identities of all descendants.')


def main():
    parent,seal,freeze=verify_full();base=Path('results/v3');execution=read(base/'v6repro_r1_reference_execution.json')
    assert execution['freeze_sha256']==sha(PATH)
    assert sha('/etc/supervisor/conf.d/cacheflow_v2_gateway.conf')==execution['original_supervisor_sha256']
    steps=freeze['actions'];missing=[s['run_id'] for s in steps if not (base/(s['run_id']+'.archive.json')).exists()]
    if missing:
        (base/'v6repro_r1_reference_incomplete.json').write_text(json.dumps(dict(complete=False,missing=missing,scope='No complete-stage successful-only table'),indent=2)+'\n')
        raise RuntimeError('Full study incomplete; inspect retained failures/outcomes')
    outcomes=read(base/'v6repro_r1_reference_outcomes.json')['runs'];assert len(outcomes)==30
    outcome={r['run_id']:r for r in outcomes};runs=[];maps={};qualities={};fullaudits={};evaluator_hashes=set();pids=set()
    for step in steps:
        rid=step['run_id'];sg=step['engine']=='sg';raw=base/'raw/sglang' if sg else base/'raw';meta=base/'sglang' if sg else base
        ap=base/(rid+'.full_audit.json');zp=base/(rid+'.archive.json');qpath=base/(rid+'.full_quality.json');a=read(ap)
        assert a['complete'] and a['requests']==1986 and a['errors']==0 and a['step']==step and a['freeze_sha256']==sha(PATH)
        assert outcome[rid]['complete'] and outcome[rid]['audit_sha256']==sha(ap) and outcome[rid]['archive_sha256']==sha(zp)
        assert a['quality_sha256']==sha(qpath) and a['setup_sha256']==sha(meta/(rid+'.setup.json')) and a['warm_setup_sha256']==sha(meta/(rid+'-warm.setup.json'))
        quality=read(qpath);assert quality['runs'][0]==a['quality'];evaluator_hashes.add(quality['evaluator_sha256'])
        assert a['engine_pid'] not in pids;pids.add(a['engine_pid']);qualities[rid]=a['quality'];fullaudits[rid]=a
        with expanded(zp) as manifest:
            assert manifest['audit_path']==str(ap) and manifest['audit_sha256']==sha(ap)
            assert {r['path']:r['sha256'] for r in manifest['files']}==a['raw_sha256']
            summary=read(raw/(rid+'.summary.json'));assert summary==a['summary']
            entry=None if sg else read(meta/(rid+'.v6_entrypoint.json'))
            audit_configuration(step,read(meta/(rid+'.setup.json')),summary,entry,parent,seal,freeze)
            if sg:native_integrity(rid)
            else:load(rid)
            rows=[json.loads(l) for l in (raw/(rid+'.jsonl')).read_text().splitlines()]
            maps[rid]={r['request_id']:{k:r[k] for k in ['prompt_sha256','output_hash','sample_id','qa_index']} for r in rows}
        assert len(maps[rid])==1986 and len(qualities[rid]['per_request'])==1986
        q=qualities[rid];assert q['answerable_n']==1540 and q['by_category']['5']['n']==446
        counters=a['metrics']['counter_deltas'] if sg else a['resource']['strict_counter_deltas']['vllm']
        runs.append(dict(**step,engine_pid=a['engine_pid'],lmcache_pid=a['lmcache_pid'],audit_sha256=sha(ap),archive_sha256=sha(zp),
            **{k:summary['arrival_ttft_'+k] for k in ['p50_ms','p95_ms','p99_ms']},
            duration_s=summary['duration_s'],observed_requests_per_s=summary['requests_per_s'],
            answerable_f1=q['answerable_f1'],category5_accuracy=q['by_category']['5']['mean'],output_budget_hits=q['output_budget_hits'],
            by_category=q['by_category'],secondary=a['secondary'],native_itl=a['native_itl'],
            source_counters=counters,host=a['host'],resource=a['resource'],per_conversation=a['fairness']['by_conversation'],
            max_head_bypasses=(a['fairness']['admission'] or {}).get('max_head_bypasses'),waits=a['waits']))
    assert len(pids)==len(runs)==30 and len(evaluator_hashes)==1
    process_units=fresh_process_units(runs)
    by={r['run_id']:r for r in runs};pairs=[]
    def pair(a,b):
        aa=by[a];bb=by[b];ar=maps[a];br=maps[b];assert aa['engine']==bb['engine'] and aa['budget']==bb['budget'] and aa['seed']==bb['seed']
        assert ar.keys()==br.keys() and all(ar[k]['prompt_sha256']==br[k]['prompt_sha256'] for k in ar)
        aq={r['request_id']:r for r in qualities[a]['per_request']};bq={r['request_id']:r for r in qualities[b]['per_request']}
        assert aq.keys()==bq.keys()==ar.keys()
        pairs.append(dict(a=a,b=b,engine=aa['engine'],budget=aa['budget'],seed=aa['seed'],baseline=aa['arm'],candidate=bb['arm'],
            **{k+'_delta_pct':100*(bb[k]/aa[k]-1) for k in ['p50_ms','p95_ms','p99_ms']},
            completion_p95_delta_pct=100*(bb['secondary']['completion_latency_ms']['p95']/aa['secondary']['completion_latency_ms']['p95']-1),
            f1_delta=bb['answerable_f1']-aa['answerable_f1'],category5_delta=bb['category5_accuracy']-aa['category5_accuracy'],
            output_hash_mismatches=sum(ar[k]['output_hash']!=br[k]['output_hash'] for k in ar),
            per_category_score_changes={str(c):dict(improved=sum(bq[k]['score']>aq[k]['score'] for k in aq if aq[k]['category']==c),
                decreased=sum(bq[k]['score']<aq[k]['score'] for k in aq if aq[k]['category']==c),
                equal=sum(bq[k]['score']==aq[k]['score'] for k in aq if aq[k]['category']==c)) for c in {r['category'] for r in aq.values()}},
            scope='Same prompt/trace/resource configuration, distinct fresh processes; native DFS differs in scheduler. No causal cross-engine comparison or quality-equivalence inference.'))
    for seed in [901,902,903]:
        for engine,baselines in [('main',['fifo64','bundle16']),('sg',['native_lpm','native_dfs','fifo64'])]:
            prefix=f'v6repro_r1_reference-{engine}-g6-'
            for candidate in ['union64','packing_ready']:
                for baseline in baselines:pair(prefix+baseline+f'-s{seed}',prefix+candidate+f'-s{seed}')
            pair(prefix+f'union64-s{seed}',prefix+f'packing_ready-s{seed}')
    for candidate in ['union64','packing_ready']:pair('v6repro_r1_reference-sg-g10-native_lpm-s901',f'v6repro_r1_reference-sg-g10-{candidate}-s901')
    pair('v6repro_r1_reference-sg-g10-union64-s901','v6repro_r1_reference-sg-g10-packing_ready-s901')
    assert len(pairs)==39
    groups=defaultdict(list)
    for p in pairs:groups[(p['engine'],p['budget'],p['baseline'],p['candidate'])].append(p)
    intervals=[]
    for (engine,budget,baseline,candidate),pp in groups.items():
        pp.sort(key=lambda p:p['seed']);assert len(pp) in {1,3}
        intervals.append(dict(engine=engine,budget=budget,baseline=baseline,candidate=candidate,metrics={k:paired_log_interval([by[p['a']][k] for p in pp],[by[p['b']][k] for p in pp]) for k in ['p50_ms','p95_ms','p99_ms']}))
    result=dict(complete=True,freeze_sha256=sha(PATH),requests=59580,errors=0,separate_warmup_requests=1800,process_units=process_units,
        unique_qa=1986,runs=runs,pairs=pairs,exploratory_run_intervals=intervals,
        scope=freeze['scope'],limitations='Means/intervals concern repeated serving schedules on one fixed dataset/model/host. n3log-ratio t intervals have unverified assumptions; single-seed larger-cache control has no interval. These are not1986independent system replicates, fresh semantic holdout, quality equivalence, exact token ITL, production liveness or a SOTA result.')
    (base/'v6repro_r1_reference_audit.json').write_text(json.dumps(result,indent=2)+'\n');print('Full study audited',result['requests'],'requests',flush=True)
    subprocess.run([sys.executable,'scripts/v6_normalize_registry.py'],check=True)


if __name__=='__main__':main()
