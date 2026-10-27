"""Reopen all18archives, recompute per-run audit and retain every matched pair."""
from collections import defaultdict
from v7_epoch_study import BASE,PREFIX,FREEZE,read,write,verify
from v7_audit_epoch_run import audit_run,rows
from v6_raw_archive import sha,expanded
from v5_run_intervals import paired_log_interval


def fresh_units(runs):
    assert len(runs)==18 and sum(r['step']['engine']=='main' for r in runs)==9
    engines=[r['engine_pid'] for r in runs];caches=[r['lmcache_pid'] for r in runs if r['step']['engine']=='main']
    for values,count in [(engines,18),(caches,9)]:
        assert all(isinstance(p,int) and not isinstance(p,bool) and p>0 for p in values)
        assert len(set(values))==count,'Retained serving process across arms'
    assert all(r['lmcache_pid'] is None for r in runs if r['step']['engine']=='sg')
    return dict(distinct_engine_pids=18,distinct_main_lmcache_pids=9)


def compare(a,b,ar,br):
    assert a['step']['engine']==b['step']['engine'] and a['step']['seed']==b['step']['seed']
    for key in ['trace_sha256','model_revision','source_sha256','gpu_kv_bytes','max_model_len','output_tokens_budget','prompt_version','request_read_timeout_s','request_pool_timeout_s','client_keepalive_connections']:
        assert a['summary'][key]==b['summary'][key],key
    assert a['engine_pid']!=b['engine_pid']
    if a['step']['engine']=='main':assert a['lmcache_pid']!=b['lmcache_pid']
    aq={r['request_id']:r for r in a['quality']['per_request']};bq={r['request_id']:r for r in b['quality']['per_request']}
    assert ar.keys()==br.keys()==aq.keys()==bq.keys() and len(ar)==60
    assert all(ar[k]['prompt_sha256']==br[k]['prompt_sha256'] and ar[k]['input_tokens']==br[k]['input_tokens'] and aq[k]['category']==bq[k]['category'] for k in ar)
    ac={r['sample_id']:r for r in a['fairness']['by_conversation']};bc={r['sample_id']:r for r in b['fairness']['by_conversation']};assert ac.keys()==bc.keys()
    return dict(a=a['run_id'],b=b['run_id'],engine=a['step']['engine'],seed=a['step']['seed'],baseline=a['step']['arm'],candidate=b['step']['arm'],
        **{q+'_delta_pct':100*(b['summary']['arrival_ttft_'+q]/a['summary']['arrival_ttft_'+q]-1) for q in ['p50_ms','p95_ms','p99_ms']},
        completion_p95_delta_pct=100*(b['secondary']['completion_latency_ms']['p95']/a['secondary']['completion_latency_ms']['p95']-1),
        f1_delta=b['quality']['answerable_f1']-a['quality']['answerable_f1'],output_hash_mismatches=sum(ar[k]['output_hash']!=br[k]['output_hash'] for k in ar),
        per_category_score_changes={str(c):dict(improved=sum(bq[k]['score']>aq[k]['score'] for k in ar if aq[k]['category']==c),
            decreased=sum(bq[k]['score']<aq[k]['score'] for k in ar if aq[k]['category']==c),equal=sum(bq[k]['score']==aq[k]['score'] for k in ar if aq[k]['category']==c)) for c in {r['category'] for r in aq.values()}},
        per_conversation_p95_delta_pct={k:100*(bc[k]['arrival_ttft_ms']['p95']/ac[k]['arrival_ttft_ms']['p95']-1) for k in ac})


def audit():
    _,_,f=verify(True);output=BASE/(PREFIX+'_audit.json');assert not output.exists()
    execution=read(BASE/(PREFIX+'_execution.json'));assert execution['freeze_sha256']==sha(FREEZE) and execution['actions']==f['actions']
    from v7_epoch_dev import CONFIG,MARKER
    assert sha(CONFIG)==execution['original_supervisor_sha256'] and not MARKER.exists(),'Controller must restore configuration before terminal audit'
    outcomes=read(BASE/(PREFIX+'_outcomes.json'))['runs'];assert [r['run_id'] for r in outcomes]==[s['run_id'] for s in f['actions']]
    runs=[];requests={};evaluator_hashes=set()
    for step,outcome in zip(f['actions'],outcomes):
        rid=step['run_id'];ap=BASE/(rid+'.v7_audit.json');zp=BASE/(rid+'.v7_archive.json');a=read(ap)
        assert outcome['complete'] is True and outcome['audit_sha256']==sha(ap) and outcome['archive_sha256']==sha(zp)
        assert a['complete'] is True and a['requests']==60 and a['errors']==0 and a['step']==step and a['freeze_sha256']==sha(FREEZE)
        qp=BASE/(rid+'.v7_quality.json');q=read(qp);assert sha(qp)==a['quality_sha256'] and q['runs'][0]==a['quality'];evaluator_hashes.add(q['evaluator_sha256'])
        with expanded(zp) as z:
            assert z['audit_sha256']==sha(ap) and {r['path']:r['sha256'] for r in z['files']}==a['raw_sha256']
            assert audit_run(rid,publish=False)==a,'Recomputed per-run evidence differs'
            raw=BASE/'raw/sglang' if step['engine']=='sg' else BASE/'raw'
            requests[rid]={r['request_id']:r for r in rows(raw/(rid+'.jsonl'))}
        runs.append(a)
    units=fresh_units(runs);assert len(evaluator_hashes)==1
    by={r['run_id']:r for r in runs};pairs=[];diagnostics=[]
    for engine,strong in [('main','bundle16'),('sg','native_dfs')]:
        for seed in [101,102,103]:
            prefix=f'v7dev1-epoch-{engine}-';suffix=f'-s{seed}'
            for baseline in ['union64',strong]:
                aa=prefix+baseline+suffix;bb=prefix+'epoch_union64'+suffix
                pairs.append(compare(by[aa],by[bb],requests[aa],requests[bb]))
            aa=prefix+strong+suffix;bb=prefix+'union64'+suffix
            diagnostics.append(compare(by[aa],by[bb],requests[aa],requests[bb]))
    assert len(pairs)==12 and len(diagnostics)==6
    groups=defaultdict(list)
    for p in pairs:groups[(p['engine'],p['baseline'])].append(p)
    intervals=[]
    for (engine,baseline),pp in groups.items():
        pp.sort(key=lambda p:p['seed']);assert [p['seed'] for p in pp]==[101,102,103]
        intervals.append(dict(engine=engine,baseline=baseline,candidate='epoch_union64',
            metrics={q:paired_log_interval([by[p['a']]['summary']['arrival_ttft_'+q] for p in pp],[by[p['b']]['summary']['arrival_ttft_'+q] for p in pp]) for q in ['p50_ms','p95_ms','p99_ms']}))
    write(output,dict(complete=True,freeze_sha256=sha(FREEZE),requests=1080,errors=0,separate_warmup_requests=1080,unique_qa=60,
        process_units=units,runs=runs,primary_pairs=pairs,secondary_baseline_diagnostics=diagnostics,exploratory_run_intervals=intervals,
        scope=f['scope'],limitations='Complete development stage only. Repeated schedules on60exposedQA, not full confirmation or independent QA replications. n3log-ratio intervals have unverified assumptions. No quality equivalence, universal gain or completed research claim.'))
    print('V7 development audited1080requests; controls/fullconfirmation still required',flush=True)


if __name__=='__main__':audit()
