import sys as _namespace_sys
from pathlib import Path as _NamespacePath
_namespace_sys.path.insert(1, str(_NamespacePath(__file__).resolve().parents[2]))
"""Prospective full-study seal; never starts serving or overwrites a seal."""
import hashlib
import json
import math
import importlib.metadata
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
from v5_verify import verify
from v6_full_plan import build_plan

PATH=Path('results/v3/v6repro_r1_reference_freeze.json')
PLAN=Path('docs/reproductions/v6repro_r1_reference.md')
ACTORS=['scripts/reproductions/v6repro_r1_reference/v6_full.py','scripts/reproductions/v6repro_r1_reference/v6_full_plan.py','scripts/reproductions/v6repro_r1_reference/v6_freeze_full.py',
    'scripts/v6_runtime.py','scripts/v6_serve_gateway.sh','src/cacheflow/v6_gateway.py',
    'src/cacheflow/v6_ready_scheduler.py','src/cacheflow/v6_replay.py','scripts/v6_run.sh',
    'scripts/v6_v2_run.sh','scripts/v6_sglang_bench.py','scripts/v6_native_metrics.py',
    'scripts/v5_full_histograms.py','scripts/v3_sglang_runtime.py','scripts/v3_serve_sglang.sh',
    'scripts/sglang_profile_hooks/sitecustomize.py','src/cacheflow/v4_sglang_delayhit.py',
    'scripts/v6_raw_archive.py','scripts/reproductions/v6repro_r1_reference/v6_token_fingerprints.py','scripts/reproductions/v6repro_r1_reference/v6_full_input_preflight.py','scripts/v6_input_oracle.py','scripts/v6_trace_hashes.py','src/cacheflow/locomo.py',
    'src/cacheflow/collect_metrics.py','src/cacheflow/v2_metrics.py','scripts/v2_extract_gateway.py',
    'scripts/v3_model.py','scripts/v4_services.py','scripts/v2_start.sh','scripts/v2_reset.sh','scripts/v2_preflight.py']
ANALYSIS=['scripts/reproductions/v6repro_r1_reference/v6_audit_full_run.py','scripts/reproductions/v6repro_r1_reference/v6_audit_full.py','scripts/reproductions/v6repro_r1_reference/v6_full_contracts.py',
    'scripts/v3_analyze_runs.py','scripts/v4_audit_sglang_runs.py','scripts/v2_quality_audit.py',
    'data/processed/v2/evaluator/evaluation.py','scripts/v6_main_resources.py','scripts/v6_native_resources.py',
    'scripts/v4_analyze_sglang_resources.py','scripts/v6_analyze_fairness.py','scripts/v3_audit_admission.py','scripts/v5_analyze_decode.py',
    'scripts/v5_analyze_histograms.py','scripts/v5_analyze_waits.py','scripts/v5_run_intervals.py',
    'scripts/v6_normalize_registry.py']
PREREQUISITES=[('results/v3/v6dev1_main_audit.json',24,1440),
    ('results/v3/sglang/v6native1_audit.json',60,2700),
    ('results/v3/v6controls1_main_audit.json',36,1260)]


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def validate_prerequisite(name,audit,expected_runs,expected_requests):
    """Accept the terminal main24 legacy schema without rewriting its audit."""
    assert audit['errors']==0 and audit['requests']==expected_requests,name
    runs=audit['runs'];assert len(runs)==expected_runs,name
    assert len({r['run_id'] for r in runs})==expected_runs,name
    assert sum(r['requests'] for r in runs)==expected_requests,name
    if str(name)=='results/v3/v6dev1_main_audit.json':
        assert (expected_runs,expected_requests)==(24,1440)
        assert audit['scope'].startswith('Complete24-arm development matrix:'),name
        assert audit.get('complete',True) is True,name
    else:
        assert audit['complete'] is True,name


def lowreuse_gates(audits):
    """Read each producer's explicit schema; require all three registered seeds."""
    gates={}
    for stack,baseline,metric in [('main','fifo64','p95_ms_delta_pct'),('sg','native','p95_delta_pct')]:
        audit=audits[stack]
        assert audit['complete'] and audit['errors']==0
        for candidate in ['union64','packing_ready']:
            pairs=[r for r in audit['pairs'] if r['regime']=='lowreuse' and r['baseline']==baseline and r['candidate']==candidate]
            assert len(pairs)==3 and {r['seed'] for r in pairs}=={101,102,103},(stack,candidate,'Incomplete seeds')
            pairs.sort(key=lambda r:r['seed'])
            values=[r[metric] for r in pairs]
            assert all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in values),(stack,candidate,'Invalid p95 deltas')
            gates[stack+'_'+candidate]=dict(seeds=[r['seed'] for r in pairs],source_metric=metric,
                per_seed_p95_delta_pct=values,passes=all(v<=5 for v in values),threshold_pct=5)
        assert gates[stack+'_union64']['passes'],'Original-union primary fails existing low-reuse gate; inspect controls before full freeze'
    return gates


def verify_full():
    parent,seal=verify();freeze=json.loads(PATH.read_text())
    assert freeze['actions']==build_plan() and freeze['plan_sha256']==sha(PLAN)
    assert all(importlib.metadata.version(n)==v for n,v in freeze['main_package_versions'].items())
    assert freeze['parent_v5_prompt_seal_sha256']==sha('results/v3/v5_prompt_freeze.json')
    for key in ['actor_sha256','analysis_source_sha256','input_manifest_sha256','input_file_sha256','model_artifact_sha256','tokenizer_source_sha256','preflight_artifact_sha256','prerequisite_audit_sha256']:
        for name,digest in freeze[key].items():assert sha(name)==digest,(key,name)
    expected=freeze['native_tokenizer_package_versions']
    versions=json.loads(subprocess.check_output(['/venv/sglang-baseline/bin/python','-c',
        'import importlib.metadata as m,json,sys;print(json.dumps({n:m.version(n) for n in json.loads(sys.argv[1])}))',json.dumps(list(expected))],text=True))
    assert versions==expected
    return parent,seal,freeze


def main():
    parent,seal=verify();assert not PATH.exists();steps=build_plan()
    for name,runs,requests in PREREQUISITES:
        validate_prerequisite(name,json.loads(Path(name).read_text()),runs,requests)
    gates=lowreuse_gates({stack:json.loads(Path(path).read_text()) for stack,path in
        [('main','results/v3/v6controls1_main_audit.json'),('sg','results/v3/sglang/v6native1_audit.json')]})
    # This is breadth evaluation of exposed QA. Both union variants remain fixed
    # treatments; the freeze does not select a winner from full-study outcomes.
    traces={s['trace'] for s in steps}|{'data/processed/v3/v5-dev4b3-qps4-s101.jsonl'}
    manifests={str(Path(t).with_suffix('.manifest.json')) for t in traces}
    for step in steps:
        m=json.loads(Path(step['trace']).with_suffix('.manifest.json').read_text())
        assert m['requests']==1986 and m['model_revision']==parent['model_revision']
        assert m['prompt_version']=='locomo-qwen-concise-v5' and m['abstention_style']=='official_consistent_system_and_user'
    from v3_model import get_model
    model=get_model('qwen3-4b');adoption=json.loads(Path(model['adoption']).read_text())
    assert adoption['revision']==parent['model_revision'] and adoption['repo']==model['repo']
    modelroot=Path(model['path']);index=json.loads((modelroot/'model.safetensors.index.json').read_text())
    assert set(index['weight_map'].values())=={r['file'] for r in adoption['weights']}
    modelpins={str(modelroot/r['file']):r['sha256'] for r in adoption['weights']}
    for name,digest in modelpins.items():assert sha(name)==digest,name
    for path in modelroot.iterdir():
        if path.is_file() and path.suffix in {'.json','.jinja'}:modelpins[str(path)]=sha(path)
    assert sha('data/raw/locomo10.json')==parent['source_data_sha256']
    traces|={model['adoption'],'data/raw/locomo10.json'}
    from v4_services import service_pid
    for name in ['cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache','cacheflow_v3_sglang']:assert service_pid(name)==0,name
    from v6_full_input_preflight import compare
    preflightpath=Path('results/v3/v6repro_r1_reference_input_preflight.json')
    if not preflightpath.exists():subprocess.run([sys.executable,'scripts/reproductions/v6repro_r1_reference/v6_full_input_preflight.py'],check=True)
    preflight=json.loads(preflightpath.read_text());assert preflight['complete'] and preflight['requests']==1986 and preflight['token_id_mismatches']==preflight['semantic_trace_mismatches']==0
    assert preflight['source_sha256']==sha('scripts/reproductions/v6repro_r1_reference/v6_full_input_preflight.py') and preflight['worker_sha256']==sha('scripts/reproductions/v6repro_r1_reference/v6_token_fingerprints.py')
    mp=Path(preflight['main_fingerprints_path']);np=Path(preflight['native_fingerprints_path'])
    assert sha(mp)==preflight['main_fingerprints_sha256'] and sha(np)==preflight['native_fingerprints_sha256']
    main_tokens=json.loads(mp.read_text());native_tokens=json.loads(np.read_text());compare(main_tokens,native_tokens)
    for report in [main_tokens,native_tokens]:
        assert report['source_sha256']==preflight['worker_sha256'] and report['oracle_source_sha256']==sha('scripts/v6_input_oracle.py')
        assert report['canonical_implementation_sha256']==sha('scripts/v6_trace_hashes.py')
    assert all(importlib.metadata.version(n)==v for n,v in main_tokens['package_versions'].items())
    assert main_tokens['model_revision']==parent['model_revision']
    for name,digest in main_tokens['tokenizer_artifact_sha256'].items():assert modelpins[name]==digest,name
    for trace,proof in preflight['inputs'].items():assert sha(trace)==proof['stored_sha256'] and sha(Path(trace).with_suffix('.manifest.json'))==proof['manifest_sha256']
    preflight_files=[preflightpath,mp,np,Path(preflight['registration_path'])]
    assert sha(preflight_files[-1])==preflight['registration_sha256']
    native=json.loads(Path('results/v3/sglang/v6native1_registration.json').read_text())
    for name in ['sglang','transformers']:assert native_tokens['package_versions'][name]==native['package_versions'][name]
    freeze=dict(status='frozen_prospective_full_study_not_completion',frozen_utc=datetime.now(timezone.utc).isoformat(),
        lowreuse_gate_status=gates,actions=steps,actor_sha256={n:sha(n) for n in ACTORS},analysis_source_sha256={n:sha(n) for n in ANALYSIS},plan_sha256=sha(PLAN),
        parent_v5_prompt_seal_sha256=sha('results/v3/v5_prompt_freeze.json'),
        prerequisite_audit_sha256={n:sha(n) for n,_,_ in PREREQUISITES},
        input_file_sha256={n:sha(n) for n in traces},input_manifest_sha256={n:sha(n) for n in manifests},
        preflight_artifact_sha256={str(n):sha(n) for n in preflight_files},tokenizer_source_sha256=native_tokens['native_source_sha256'],native_tokenizer_package_versions=native_tokens['package_versions'],
        main_package_versions={n:importlib.metadata.version(n) for n in ['vllm','lmcache','torch','transformers','tokenizers','httpx','numpy','nltk','regex','PyYAML','psutil']},native_package_versions=native['package_versions'],native_source_sha256=native['upstream_source_sha256'],
        model_artifact_sha256=modelpins,model_revision=parent['model_revision'],source_data_sha256=parent['source_data_sha256'],
        transport=dict(read_s=3600,pool_s=3600,keepalive=0),host_payload_bytes=48002236416,
        expected_main_heap_bytes=48049946624,expected_native_host_bytes=48002236416,
        scope='30complete1986QA arms on exposed semantic data, fresh engine+separate60warmup per arm. No quality equivalence/SOTA/liveness claim. Original union and readiness remain separate treatments; preserve all failures and no retries.')
    PATH.write_text(json.dumps(freeze,indent=2)+'\n');verify_full();print('Prospective full seal written',sha(PATH),flush=True)


if __name__=='__main__':main()
