"""Immutable interim evidence from the exact audited prefix of the full study.

Never includes partial/error-arm quantiles, replays inference or replaces the
terminal30-arm audit. Secondary baseline contrasts are labelled separately.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from v5_verify import verify
from v6_freeze_full import PATH,sha
from v6_full_analysis_r1 import REGISTRATION,audit_configuration
from v6_full_continuation_r1 import verify_continuation,retained_outcome
from v6_full_load_r1 import load
from v6_raw_archive import expanded
from v4_audit_sglang_runs import audit as native_integrity
from v5_run_intervals import paired_log_interval

BASE=Path('results/v3')


def read(path):return json.loads(Path(path).read_text())


def planned_pairs():
    pairs=[]
    for seed in [901,902,903]:
        for engine,baselines in [('main',['fifo64','bundle16']),('sg',['native_lpm','native_dfs','fifo64'])]:
            prefix=f'v6full1-{engine}-g6-'
            for candidate in ['union64','packing_ready']:
                for baseline in baselines:pairs.append((prefix+baseline+f'-s{seed}',prefix+candidate+f'-s{seed}'))
            pairs.append((prefix+f'union64-s{seed}',prefix+f'packing_ready-s{seed}'))
    for candidate in ['union64','packing_ready']:pairs.append(('v6full1-sg-g10-native_lpm-s901',f'v6full1-sg-g10-{candidate}-s901'))
    pairs.append(('v6full1-sg-g10-union64-s901','v6full1-sg-g10-packing_ready-s901'))
    assert len(pairs)==39 and len(set(pairs))==39
    return pairs


def compare(a,b,ar,br,aq,bq):
    for key in ['engine','budget','seed']:assert a['step'][key]==b['step'][key],key
    for key in ['trace_sha256','model_revision','source_sha256','gpu_kv_bytes','max_model_len','output_tokens_budget','request_read_timeout_s','request_pool_timeout_s','client_keepalive_connections']:
        assert a['summary'][key]==b['summary'][key],key
    assert a['engine_pid']!=b['engine_pid']
    if a['step']['engine']=='main':assert a['lmcache_pid']!=b['lmcache_pid']
    assert ar.keys()==br.keys()==aq.keys()==bq.keys() and len(ar)==1986
    assert all(ar[k]['prompt_sha256']==br[k]['prompt_sha256'] and ar[k]['input_tokens']==br[k]['input_tokens'] and ar[k]['sample_id']==br[k]['sample_id'] and ar[k]['qa_index']==br[k]['qa_index'] for k in ar),'Changed prompt/QA'
    assert all(aq[k]['category']==bq[k]['category'] for k in aq)
    out=dict(a=a['run_id'],b=b['run_id'],engine=a['step']['engine'],budget=a['step']['budget'],seed=a['step']['seed'],
        baseline=a['step']['arm'],candidate=b['step']['arm'],
        **{q+'_delta_pct':100*(b['summary']['arrival_ttft_'+q]/a['summary']['arrival_ttft_'+q]-1) for q in ['p50_ms','p95_ms','p99_ms']},
        completion_p95_delta_pct=100*(b['secondary']['completion_latency_ms']['p95']/a['secondary']['completion_latency_ms']['p95']-1),
        f1_delta=b['quality']['answerable_f1']-a['quality']['answerable_f1'],
        category5_delta=b['quality']['by_category']['5']['mean']-a['quality']['by_category']['5']['mean'],
        output_hash_mismatches=sum(ar[k]['output_hash']!=br[k]['output_hash'] for k in ar),
        per_category_score_changes={str(c):dict(improved=sum(bq[k]['score']>aq[k]['score'] for k in aq if aq[k]['category']==c),
            decreased=sum(bq[k]['score']<aq[k]['score'] for k in aq if aq[k]['category']==c),equal=sum(bq[k]['score']==aq[k]['score'] for k in aq if aq[k]['category']==c)) for c in sorted({r['category'] for r in aq.values()})})
    aa={r['sample_id']:r for r in a['fairness']['by_conversation']};bb={r['sample_id']:r for r in b['fairness']['by_conversation']}
    assert aa.keys()==bb.keys()
    out['per_conversation_p95_delta_pct']={k:100*(bb[k]['arrival_ttft_ms']['p95']/aa[k]['arrival_ttft_ms']['p95']-1) for k in aa}
    return out


def checkpoint(output):
    output=Path(output);assert not output.exists()
    parent,seal=verify();registration=verify_continuation();freeze=read(PATH)
    for group in ['actor_sha256','analysis_source_sha256','prerequisite_audit_sha256']:
        for name,digest in freeze[group].items():assert sha(name)==digest,(group,name)
    assert sha('docs/V6_FULL_PROTOCOL.md')==freeze['plan_sha256']
    outcome_path=BASE/'v6full1_continuation_r1_outcomes.json'
    outcomes=read(outcome_path)['runs'] if outcome_path.exists() else [retained_outcome()]
    assert [r['run_id'] for r in outcomes]==[s['run_id'] for s in freeze['actions'][:len(outcomes)]]
    assert 1<=len(outcomes)<=30 and all(r['complete'] is True for r in outcomes)
    audits={};requests={};scores={};runs=[];evaluators=set()
    for step,outcome in zip(freeze['actions'],outcomes):
        rid=step['run_id'];sg=step['engine']=='sg';meta=BASE/'sglang' if sg else BASE;raw=BASE/'raw/sglang' if sg else BASE/'raw'
        ap=BASE/(rid+'.full_audit_r1.json');zp=BASE/(rid+'.archive_r1.json');qp=BASE/(rid+'.full_quality_r1.json');a=read(ap)
        assert sha(ap)==outcome['audit_sha256'] and sha(zp)==outcome['archive_sha256']
        assert a['complete'] is True and a['requests']==1986 and a['errors']==0 and a['step']==step
        assert a['freeze_sha256']==sha(PATH) and a['analysis_revision_registration_sha256']==sha(REGISTRATION)
        assert a['quality_sha256']==sha(qp) and a['setup_sha256']==sha(meta/(rid+'.setup.json')) and a['warm_setup_sha256']==sha(meta/(rid+'-warm.setup.json'))
        q=read(qp);assert q['runs'][0]==a['quality'];evaluators.add(q['evaluator_sha256'])
        with expanded(zp) as manifest:
            assert manifest['audit_sha256']==sha(ap) and {r['path']:r['sha256'] for r in manifest['files']}==a['raw_sha256']
            summary=read(raw/(rid+'.summary.json'));assert summary==a['summary']
            entry=None if sg else read(meta/(rid+'.v6_entrypoint.json'))
            audit_configuration(step,read(meta/(rid+'.setup.json')),summary,entry,parent,seal,freeze)
            if sg:native_integrity(rid)
            else:load(rid)
            rr=[json.loads(line) for line in (raw/(rid+'.jsonl')).read_text().splitlines()]
            requests[rid]={r['request_id']:{k:r[k] for k in ['prompt_sha256','input_tokens','output_hash','sample_id','qa_index']} for r in rr}
        scores[rid]={r['request_id']:r for r in a['quality']['per_request']}
        assert len(requests[rid])==len(scores[rid])==1986
        audits[rid]=a
        runs.append(dict(run_id=rid,step=step,summary=summary,quality={k:v for k,v in a['quality'].items() if k!='per_request'},
            secondary=a['secondary'],host=a['host'],resource=a['resource'],native_itl=a['native_itl'],waits=a['waits'],
            per_conversation=a['fairness']['by_conversation'],audit_sha256=sha(ap),archive_sha256=sha(zp)))
    assert len(evaluators)==1
    def pairs_available(planned,label):
        return [compare(audits[a],audits[b],requests[a],requests[b],scores[a],scores[b])|dict(scope=label)
            for a,b in planned if a in audits and b in audits]
    pairs=pairs_available(planned_pairs(),'Registered full primary comparison, available completed pair only; study incomplete')
    secondary_plan=[(f'v6full1-main-g6-fifo64-s{s}',f'v6full1-main-g6-bundle16-s{s}') for s in [901,902,903]]
    secondary_pairs=pairs_available(secondary_plan,'Supplemental baseline-strength diagnostic; separate from the39registered primary contrasts')
    groups=defaultdict(list)
    for pair in pairs:groups[(pair['engine'],pair['budget'],pair['baseline'],pair['candidate'])].append(pair)
    intervals=[]
    for key,pp in groups.items():
        if len(pp)==3:
            pp.sort(key=lambda p:p['seed']);assert [p['seed'] for p in pp]==[901,902,903]
            intervals.append(dict(group=list(key),p95=paired_log_interval([audits[p['a']]['summary']['arrival_ttft_p95_ms'] for p in pp],[audits[p['b']]['summary']['arrival_ttft_p95_ms'] for p in pp])))
    result=dict(complete=False,kind='interim_full_checkpoint_not_terminal_audit',completed_arms=len(runs),measured_requests=1986*len(runs),
        scheduled_full_arms=30,scheduled_full_requests=59580,unique_qa=1986,separate_completed_warmup_requests=60*len(runs),
        freeze_sha256=sha(PATH),continuation_registration_sha256=sha('results/v3/v6full1_continuation_r1_registration.json'),source_sha256=sha(__file__),
        outcomes_sha256=sha(outcome_path) if outcome_path.exists() else None,runs=runs,available_primary_pairs=pairs,
        available_secondary_baseline_pairs=secondary_pairs,exploratory_complete_three_seed_intervals=intervals,
        pending_run_ids=[s['run_id'] for s in freeze['actions'][len(runs):]],
        scope='Only the exact completed audited prefix; raw archives reopened and request/config/output/quality identities checked. No model-weight rehash or serving calls in this observer. Pending/error arms have no partial quantiles. Single-seed results have no interval; quality differences are not equivalence. Full completion still requires the separate30-arm terminal audit.')
    with output.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print('Audited checkpoint',len(runs),'arms,',len(pairs),'primary pairs,',len(secondary_pairs),'secondary baseline pairs',flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();checkpoint(a.output)
