"""V7 development seal and prerequisite gates, separate from original studies."""
import argparse
import importlib.metadata
import hashlib
import json
import math
import subprocess
from datetime import datetime,timezone
from pathlib import Path
from v5_verify import verify as verify_parent
from v6_freeze_full import ACTORS,ANALYSIS,verify_full
from v6_raw_archive import sha
from v6_after_input_reproduction import validate_input_result
from v6_regenerate_full_inputs import idle
from v7_epoch_plan import build_plan
from v7_collector_source import native_source
from v7_epoch_contract_source import configuration_source
from cacheflow.v6_replay import load_trace
from cacheflow.locomo import trace_digest

BASE=Path('results/v3');PREFIX='v7dev1_epoch';FREEZE=BASE/(PREFIX+'_freeze.json');PROTOCOL=Path('docs/V7_EPOCH_DEV_PROTOCOL.md')
EXTRA=['scripts/v7_epoch_study.py','scripts/v7_epoch_dev.py','scripts/v7_audit_epoch_run.py','scripts/v7_audit_epoch_dev.py',
    'scripts/v7_epoch_contract_source.py','scripts/v7_epoch_contracts.py','scripts/v7_epoch_plan.py','scripts/v7_gateway_identity.py',
    'scripts/v7_run.sh','scripts/v7_serve_gateway.sh','scripts/v7_sglang_bench.py','scripts/v7_collector_source.py',
    'src/cacheflow/v7_gateway.py','src/cacheflow/v7_epoch_scheduler.py','scripts/v6_full_analysis_r1.py',
    'scripts/v6_after_input_reproduction.py','scripts/v6_regenerate_full_inputs.py','scripts/v5_verify.py','scripts/v7_after_epoch_trace.py']
PROOFS={'full':BASE/'v6full1_audit_r1.json',
    'inputs':BASE/'v6full1_input_regeneration_registration.result.json',
    'namespace':BASE/'v6full1_r1_namespace_preparation_registration.result.json',
    'cpu':BASE/'v7_epoch_cpu_probe_registration.result.json',
    'trace':BASE/'v7_epoch_trace_check_registration.result.json'}


def read(p):return json.loads(Path(p).read_text())


def write(p,value):
    with Path(p).open('x') as out:out.write(json.dumps(value,indent=2)+'\n')


def full_pairs(original):
    by={(s['engine'],s['budget'],s['seed'],s['arm']):s['run_id'] for s in original['actions']};pairs=set()
    for seed in [901,902,903]:
        for engine,baselines in [('main',['fifo64','bundle16']),('sg',['native_lpm','native_dfs','fifo64'])]:
            for candidate in ['union64','packing_ready']:
                for baseline in baselines:pairs.add((by[engine,6,seed,baseline],by[engine,6,seed,candidate]))
            pairs.add((by[engine,6,seed,'union64'],by[engine,6,seed,'packing_ready']))
    for baseline,candidate in [('native_lpm','union64'),('native_lpm','packing_ready'),('union64','packing_ready')]:pairs.add((by['sg',10,901,baseline],by['sg',10,901,candidate]))
    assert len(pairs)==39;return pairs


def validate_prerequisites(proofs,original):
    full=proofs['full'];assert full['complete'] is True and full['requests']==59580 and full['errors']==0
    assert len(full['runs'])==30 and len(full['pairs'])==39 and full['unique_qa']==1986 and full['separate_warmup_requests']==1800
    assert [r['run_id'] for r in full['runs']]==[r['run_id'] for r in original['actions']]
    assert {(r['a'],r['b']) for r in full['pairs']}==full_pairs(original)
    assert full['process_units']['distinct_engine_pids']==30 and full['process_units']['distinct_main_lmcache_pids']==12
    assert full['freeze_sha256']==sha(BASE/'v6full1_freeze.json')
    inp=proofs['inputs'];validate_input_result(inp,sha(BASE/'v6full1_input_regeneration_registration.json'),original)
    ns=proofs['namespace'];assert ns['complete_namespace_preparation'] is True and ns['gpu_execution'] is False
    assert ns['generated_cli_plan_equal'] is True and ns['planned_fresh_arms']==30 and ns['planned_measured_requests']==59580
    assert ns['registration_sha256']==sha(BASE/'v6full1_r1_namespace_preparation_registration.json')
    assert ns['source_input_reproduction_sha256']==sha(PROOFS['inputs']) and sha(ns['namespace_manifest_path'])==ns['namespace_manifest_sha256']
    manifest=read(ns['namespace_manifest_path']);assert len(manifest['files'])==8 and len(manifest['actions'])==30
    assert manifest['reference_freeze_sha256']==full['freeze_sha256'] and manifest['analysis_revision'] is not None
    assert sha(manifest['protocol_path'])==manifest['protocol_sha256']
    for row in manifest['files']:assert sha(row['path'])==row['sha256']
    cpu=proofs['cpu'];assert cpu['complete'] is True and cpu['synthetic'] is True and cpu['gpu_execution'] is False
    assert cpu['registration_sha256']==sha(BASE/'v7_epoch_cpu_probe_registration.json') and cpu['parent_result_sha256']==sha(PROOFS['namespace'])
    reg=read(BASE/'v7_epoch_cpu_probe_registration.json')
    expected={(p,q,k) for p in reg['policies'] for q in reg['queues'] for k in reg['kernels']}
    assert len(cpu['cases'])==45 and {(r['policy'],r['queue'],r['kernel']) for r in cpu['cases']}==expected
    assert all(len(r['samples'][kind])==reg['rounds'] for r in cpu['cases'] for kind in ['legacy','prototype'])
    assert all(math.isfinite(s['thread_cpu_ns_per_iteration']) and s['thread_cpu_ns_per_iteration']>0 for r in cpu['cases'] for kind in ['legacy','prototype'] for s in r['samples'][kind])
    tr=proofs['trace'];assert tr['complete_ledger_state_check'] is True and tr['gpu_execution'] is False
    assert tr['production_decision_trace_reproduced'] is False and tr['unique_qa']==1986 and tr['input_tokens']==50522325 and tr['request_trajectories']==3972
    assert tr['registration_sha256']==sha(BASE/'v7_epoch_trace_check_registration.json') and tr['parent_result_sha256']==sha(PROOFS['cpu']) and tr['terminal_full_audit_sha256']==sha(PROOFS['full'])
    assert {r['run_id'] for r in tr['runs']}==set(read(BASE/'v7_epoch_trace_check_registration.json')['target_run_ids'])
    assert len(tr['runs'])==2
    for row in tr['runs']:
        result=row['result'];assert result['requests']==1986 and result['events']==7944
        assert result['checked_state_points']==2483 and result['stable_polls_per_point']==3
        assert result['prototype_winner_reason_timeout_mismatches']==result['prototype_active_reservation_mismatches']==0
        original_run=next(r for r in full['runs'] if r['run_id']==row['run_id'])
        assert row['audit_sha256']==original_run['audit_sha256'] and row['archive_sha256']==original_run['archive_sha256']


def prerequisites():
    original=read(BASE/'v6full1_freeze.json');proofs={name:read(path) for name,path in PROOFS.items()}
    validate_prerequisites(proofs,original)
    for name in ['v6full1_analysis_r1_registration','v6full1_continuation_r1_registration','v6full1_input_regeneration_registration','v6full1_r1_namespace_preparation_registration','v7_epoch_cpu_probe_registration','v7_epoch_trace_check_registration']:
        registration=BASE/(name+'.json');assert not registration.with_suffix('.failure.json').exists(),name
        for path,digest in read(registration)['source_sha256'].items():assert sha(path)==digest,path
    return {str(path):sha(path) for path in PROOFS.values()}


def source_proof():
    assert Path('scripts/v7_sglang_bench.py').read_text()==native_source(Path('scripts/v6_sglang_bench.py').read_text())
    assert Path('scripts/v7_epoch_contracts.py').read_text()==configuration_source(Path('scripts/v6_full_contracts.py').read_text())


def source_maps():
    # Main setup snapshots enumerate src/cacheflow, scripts and configs. Keep
    # the data-directory evaluator in the independent analysis seal, not in
    # the required gateway/runtime snapshot set.
    return dict(actor_sha256={p:sha(p) for p in sorted(set(ACTORS+EXTRA))},
        analysis_source_sha256={p:sha(p) for p in ANALYSIS})


def validate_dev_inputs(actions,parent):
    semantic=set()
    for trace,seed in {s['trace']:s['seed'] for s in actions}.items():
        m=read(Path(trace).with_suffix('.manifest.json'));data=load_trace(Path(trace))
        assert m['seed']==seed and m['qps']==4 and m['requests']==len(data)==60
        assert m['max_model_len']==32768 and m['output_tokens']==96 and m['selected_samples']==['conv-26','conv-30','conv-41']
        assert m['model_revision']==parent['model_revision'] and m['source_sha256']==parent['source_data_sha256']
        assert m['prompt_version']=='locomo-qwen-concise-v5' and m['abstention_style']=='official_consistent_system_and_user'
        assert trace_digest(data)==m['trace_sha256']
        content=[dict(request_id=r.request_id,prompt=r.prompt,input_tokens=r.input_tokens,max_tokens=r.max_tokens,sample_id=r.sample_id,qa_index=r.qa_index,category=r.category,protocol=r.protocol) for r in data]
        semantic.add(hashlib.sha256(json.dumps(content,sort_keys=True).encode()).hexdigest())
    assert len(semantic)==1,'Changed non-arrival semantics across dev schedules'
    return next(iter(semantic))


def verify(heavy=False):
    parent,seal=verify_parent();f=read(FREEZE)
    assert f['status']=='frozen_prospective_v7_development_not_completion' and f['actions']==build_plan()
    assert sha(PROTOCOL)==f['protocol_sha256'];source_proof()
    for group in ['actor_sha256','analysis_source_sha256','input_file_sha256','input_manifest_sha256','prerequisite_sha256']:
        for name,digest in f[group].items():assert sha(name)==digest,(group,name)
    assert f['prerequisite_sha256']==prerequisites()
    assert all(importlib.metadata.version(k)==v for k,v in f['main_package_versions'].items())
    for name,digest in f['model_artifact_sha256'].items():
        if not name.endswith('.safetensors'):assert sha(name)==digest,name
    versions=json.loads(subprocess.check_output(['/venv/sglang-baseline/bin/python','-c',
        'import importlib.metadata as m,json,sys;print(json.dumps({n:m.version(n) for n in json.loads(sys.argv[1])}))',json.dumps(list(f['native_package_versions']))],text=True))
    assert versions==f['native_package_versions']
    if heavy:
        idle();_,_,original=verify_full()
        assert f['original_full_freeze_sha256']==sha(BASE/'v6full1_freeze.json')
        assert f['model_artifact_sha256']==original['model_artifact_sha256']
    return parent,seal,f


def freeze():
    idle();assert not FREEZE.exists();proofs=prerequisites();parent,seal,original=verify_full();source_proof()
    actions=build_plan();traces={s['trace'] for s in actions};manifest_paths={str(Path(t).with_suffix('.manifest.json')) for t in traces}
    semantic=validate_dev_inputs(actions,parent)
    for s in actions:
        root=BASE/'sglang' if s['engine']=='sg' else BASE
        assert not list(root.glob(s['run_id']+'*')),s['run_id']
    f=dict(status='frozen_prospective_v7_development_not_completion',frozen_utc=datetime.now(timezone.utc).isoformat(),
        actions=actions,protocol_sha256=sha(PROTOCOL),non_arrival_semantic_sha256=semantic,**source_maps(),
        prerequisite_sha256=proofs,input_file_sha256={p:sha(p) for p in traces|{'data/raw/locomo10.json','results/v3/qwen3_4b_adoption.json'}},input_manifest_sha256={p:sha(p) for p in manifest_paths},
        original_full_freeze_sha256=sha(BASE/'v6full1_freeze.json'),host_payload_bytes=16000745472,expected_main_heap_bytes=16039018496,expected_native_host_bytes=16000745472,
        **{k:original[k] for k in ['main_package_versions','native_package_versions','native_source_sha256','model_artifact_sha256','model_revision','source_data_sha256']},
        scope='18fresh-engine development configurations,1080measured+1080separatewarmups,60exposedQA×3arrival schedules. Same-policy optimization and strongbundle/DFS references; not full confirmation, quality equivalence, new independent semantic data or completed research. No retries; preserve all failures/regressions.')
    write(FREEZE,f);verify();print('V7 development sealed',sha(FREEZE),flush=True)
    return f


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','verify']);a=p.parse_args()
    if a.command=='freeze':freeze()
    else:verify(True);print('V7 development seal verified')
