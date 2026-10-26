"""Audit all frozen full-study runs, resource parity, paired quality and fairness.

No results are emitted until every planned run is complete and verified. Process
changes are explicitly labelled rather than passed off as same-process crossovers.
"""
import json
import statistics
import subprocess
import sys
from pathlib import Path
import numpy as np
import yaml
from v5_full import build_plan
from v4_full_contracts import audit_configuration
from v5_verify import verify
from v5_audit_contracts import audit_common
from v4_audit_sglang_runs import audit as audit_sg
from v3_analyze_runs import load as load_main
from v3_audit_admission import audit as audit_admission
from cacheflow.v4_resources import sglang_host_pool_bytes


def read(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def paired(a,b,quality,raw):
    assert a['trace_sha256']==b['trace_sha256']
    aa={r['request_id']:r for r in read(raw/f"{a['run_id']}.jsonl")}
    bb={r['request_id']:r for r in read(raw/f"{b['run_id']}.jsonl")}
    qa={r['request_id']:r for r in quality[a['run_id']]['per_request']}
    qb={r['request_id']:r for r in quality[b['run_id']]['per_request']}
    assert aa.keys()==bb.keys()==qa.keys()==qb.keys() and len(aa)==1986
    assert all(aa[k]['prompt_sha256']==bb[k]['prompt_sha256'] and aa[k]['input_tokens']==bb[k]['input_tokens'] for k in aa)
    groups=[]
    for group in sorted({r['sample_id'] for r in aa.values()}):
        ids=[k for k in aa if aa[k]['sample_id']==group]
        av=[aa[k]['arrival_ttft_ms'] for k in ids];bv=[bb[k]['arrival_ttft_ms'] for k in ids]
        groups.append(dict(sample_id=group,n=len(ids),a_mean_ms=statistics.mean(av),b_mean_ms=statistics.mean(bv),
            a_p95_ms=float(np.percentile(av,95)),b_p95_ms=float(np.percentile(bv,95))))
    categories={}
    for cat in sorted({r['category'] for r in qa.values()}):
        ids=[k for k in qa if qa[k]['category']==cat]
        changes=[qb[k]['score']-qa[k]['score'] for k in ids]
        categories[str(cat)]=dict(n=len(ids),a_mean=statistics.mean(qa[k]['score'] for k in ids),
            b_mean=statistics.mean(qb[k]['score'] for k in ids),mean_delta=statistics.mean(changes),
            improved=sum(x>0 for x in changes),worse=sum(x<0 for x in changes),equal=sum(x==0 for x in changes))
    return dict(a=a['run_id'],b=b['run_id'],comparison_scope='same process' if a['engine_pid']==b['engine_pid'] else 'fresh processes; matched semantic configuration',
        **{k+'_delta_pct':100*(b[k]/a[k]-1) for k in ['p50_ms','p95_ms','p99_ms']},
        output_hash_mismatches=sum(aa[k]['output_hash']!=bb[k]['output_hash'] for k in aa),
        categories=categories,per_conversation=groups)


def main():
    freeze,seal=verify();digest=seal['parent_method_freeze_sha256'];steps=[s for s in build_plan() if s['kind'] in {'sg','main'} and '-warm-' not in s['run_id']]
    assert len(steps)==17
    rows=[];ids={'sg':[],'main':[]};setups={}
    for step in steps:
        rid=step['run_id'];kind=step['kind'];ids[kind].append(rid)
        base=Path('results/v3/sglang' if kind=='sg' else 'results/v3')
        raw=Path('results/v3/raw/sglang' if kind=='sg' else 'results/v3/raw')
        setup=json.loads((base/f'{rid}.setup.json').read_text());setups[rid]=setup
        s=json.loads((raw/f'{rid}.summary.json').read_text());runtime=setup['runtime']
        audit_configuration(step,setup,freeze)
        assert s['request_read_timeout_s']==s['request_pool_timeout_s']==3600
        assert s['client_keepalive_connections']==0
        if setup.get('gateway_config'):assert setup['gateway_before']['upstream_read_timeout_s']==3600
        manifest=json.loads(Path(step['trace']).with_suffix('.manifest.json').read_text())
        audit_common(step,setup,s,manifest,freeze,seal)
        assert s['requests']==s['successes']==1986 and not s['errors']
        assert s['trace_sha256']==manifest['trace_sha256'] and manifest['requests']==1986
        assert manifest['parent_method_freeze_sha256']==digest
        assert s['model_revision']==freeze['model_revision'] and s['prompt_version']=='locomo-qwen-concise-v5'
        assert s['source_sha256']==freeze['source_data_sha256'] and s['output_tokens_budget']==96
        snapshots={}
        for key in ['frontend_source_sha256','native_overlay_source_sha256','gateway_source_sha256','source_files_sha256']:
            snapshots.update(setup.get(key,{}))
        assert snapshots,'missing local source fingerprints'
        for name,actual in snapshots.items():
            if name in freeze['source_sha256']:assert actual==freeze['source_sha256'][name],(rid,name)
        if kind=='sg':assert setup['reset_status']==200
        if setup.get('gateway_config'):
            cfg=yaml.safe_load(setup['gateway_config'])
            assert cfg['scheduler']['max_queue']==512
            assert setup['gateway_before']['active']==setup['gateway_before']['queue']==0
        requests=read(raw/f'{rid}.jsonl')
        assert len({(r['sample_id'],r['qa_index']) for r in requests})==1986
        assert len({r['sample_id'] for r in requests})==10
        if kind=='sg':
            row=audit_sg(rid)
            assert runtime['same_batch_guard'] and not runtime['profile_transfers']
            assert runtime['io_backend']=='direct' and runtime['attention_backend']=='flashinfer'
            assert runtime['max_running_requests']==16 and runtime['batch_tokens']==8192
            assert sglang_host_pool_bytes(runtime['host_kv_gib'],147456)==freeze['host_pool_bytes']['full']
            assert runtime['gpu_kv_gib']==(10 if '-g10-' in rid else 6)
            if setup['gateway_policy']:
                assert setup['gateway_before']['completed_history_requests']==0 and setup['gateway_before']['prepare_mode']=='thread'
        else:
            run=load_main(rid);c=run['metrics']['counter_deltas']['vllm']
            assert runtime['cpu_l1_bytes']==freeze['host_pool_bytes']['full']
            argv=setup['actual_lmcache_argv_list'];assert int(float(argv[argv.index('--l1-size-gb')+1])*2**30)==runtime['cpu_l1_bytes']
            assert runtime['prepare_in_thread'] and runtime['max_num_seqs']==16 and not runtime['enforce_eager']
            assert not any(runtime.get(k,False) for k in ['profile','kv_events','batch_invariant','residency_events'])
            assert setup['gateway_before']['completed_history_requests']==0
            row=dict(run_id=rid,requests=1986,errors=0,
                **{k:s['arrival_ttft_'+k] for k in ['p50_ms','p95_ms','p99_ms']},
                trace_sha256=s['trace_sha256'],computed_tokens=c['vllm:request_prefill_kv_computed_tokens_sum'],
                consumed_cpu_tokens=c['vllm:prompt_tokens_source_external_kv_transfer_total'],
                preemptions=c['vllm:num_preemptions_total'],admission=audit_admission(rid))
        if setup.get('gateway_config'):
            gates=read(raw/f'{rid}.gateway.jsonl')
            row['gateway_timing_ms']={key:{'p50':float(np.percentile([g[key] for g in gates],50)),
                'p95':float(np.percentile([g[key] for g in gates],95)),
                'max':max(g[key] for g in gates)} for key in ['ingress_prepare_ms','prepare_queue_ms','prepare_cpu_ms','admission_wait_ms']}
        row.update(engine_kind=kind,engine_pid=s['engine_pid'],runtime=runtime,
            duration_s=s['duration_s'],achieved_requests_per_s=s['requests_per_s'])
        rows.append(row)
    qualities={}
    for kind in ids:
        out=Path(f'results/v3/v5r2_full_{kind}_quality.json')
        subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir',
            'results/v3/raw/sglang' if kind=='sg' else 'results/v3/raw','--run-ids',*ids[kind],'--output',str(out)],check=True)
        qualities[kind]={r['run_id']:r for r in json.loads(out.read_text())['runs']}
    by={r['run_id']:r for r in rows};pairs=[]
    for seed in [901,902,903]:
        b=by[f'v5r2-full-sg-g6-qps4-union-s{seed}']
        for arm in ['native','fifo','dfs']:
            a=by[f'v5r2-full-sg-g6-qps4-{arm}-s{seed}']
            sa=setups[a['run_id']];sb=setups[b['run_id']]
            ra=dict(sa['runtime']);rb=dict(sb['runtime'])
            ra.pop('schedule_policy');rb.pop('schedule_policy');assert ra==rb
            assert sa['upstream_source_sha256']==sb['upstream_source_sha256']
            pairs.append(paired(a,b,qualities['sg'],Path('results/v3/raw/sglang')))
    pairs.append(paired(by['v5r2-full-sg-g10-qps4-native-s901'],by['v5r2-full-sg-g10-qps4-union-s901'],qualities['sg'],Path('results/v3/raw/sglang')))
    for arm in ['fifo64','bundle16']:
        pairs.append(paired(by[f'v5r2-full-main-g6-qps4-{arm}-s901'],by['v5r2-full-main-g6-qps4-union64-s901'],qualities['main'],Path('results/v3/raw')))
    result=dict(scope='All1986QA;3 primary serving seeds repeat the same questions. Resource control and main-stack supplement each have one seed. Category5 is separate from answerable F1.',
        parent_method_freeze_sha256=digest,requests=sum(r['requests'] for r in rows),errors=0,runs=rows,pairs=pairs)
    Path('results/v3/v5r2_full_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Verified full study',result['requests'],'requests',len(rows),'runs',flush=True)


if __name__=='__main__':main()
