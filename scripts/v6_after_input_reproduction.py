"""Prepare an R1-corrected fresh namespace only after full input proof succeeds.

No freezing, engine startup or inference: the sole generated CLI call is --plan.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
import psutil
from v6_raw_archive import sha
from v6_regenerate_full_inputs import wait_parent,idle,FREEZE
from v6_reproduce_namespace import prepare,mapping

INPUT_REGISTRATION=Path('results/v3/v6full1_input_regeneration_registration.json')


def validate_input_result(proof,registration_sha,freeze):
    assert proof['complete'] is True and proof['cpu_only'] is True
    assert proof['registration_sha256']==registration_sha
    assert proof['unique_qa']==1986 and proof['answerable']==1540 and proof['category5']==446 and proof['input_tokens']==50522325
    assert proof['prompt_and_token_fingerprints_equal'] is True and proof['original_inputs_unchanged'] is True
    expected={s['trace']:s['seed'] for s in freeze['actions']};seeds=proof['seeds']
    assert len(seeds)==3 and {p['seed'] for p in seeds}=={901,902,903}
    assert {p['original_path'] for p in seeds}==set(expected)
    for p in seeds:
        assert p['seed']==expected[p['original_path']]
        digest=freeze['input_file_sha256'][p['original_path']]
        assert p['requests']==1986 and p['generated_from_official_source'] is True
        assert p['original_stored_sha256']==p['restored_identity']['stored_sha256']==digest


def register(pid,path,namespace):
    path=Path(path);assert not path.exists();mapping(namespace)
    assert not (Path('scripts/reproductions')/namespace).exists() and not Path(f'docs/reproductions/{namespace}.md').exists()
    process=psutil.Process(pid);argv=process.cmdline()
    assert process.is_running() and process.status()!=psutil.STATUS_ZOMBIE
    assert argv[-3:]==['scripts/v6_regenerate_full_inputs.py','execute',str(INPUT_REGISTRATION)],'Unexpected dependent process'
    sources=[__file__,'scripts/v6_reproduce_namespace.py','scripts/v6_regenerate_full_inputs.py','scripts/v6_full_analysis_r1.py','scripts/v6_raw_archive.py','scripts/v4_services.py']
    r=dict(kind='prepare_r1_namespace_after_verified_from_source_inputs',registered_utc=datetime.now(timezone.utc).isoformat(),
        after_pid=pid,after_create_time=process.create_time(),after_argv=argv,namespace=namespace,
        input_registration_path=str(INPUT_REGISTRATION),input_registration_sha256=sha(INPUT_REGISTRATION),reference_freeze_sha256=sha(FREEZE),
        analysis_registration_sha256=sha('results/v3/v6full1_analysis_r1_registration.json'),source_sha256={str(p):sha(p) for p in sources},
        scope='Wait for exact input-reproduction process, require complete actual1986QA/3seedproof, idle services, then prepare8source/protocol copies and run only generated--plan. No newseal, GPUengine, inference, invalid-marker exemption or replacement of the original30-arm study.')
    with path.open('x') as output:output.write(json.dumps(r,indent=2)+'\n')
    return r


def execute(path):
    path=Path(path);r=json.loads(path.read_text());result_path=path.with_suffix('.result.json')
    assert r['kind']=='prepare_r1_namespace_after_verified_from_source_inputs'
    assert not result_path.exists() and not path.with_suffix('.failure.json').exists(),'Retain terminal attempt'
    print('Waiting on exact input-reproduction job',r['after_pid'],r['after_create_time'],flush=True)
    wait_parent(r);idle()
    for name,digest in r['source_sha256'].items():assert sha(name)==digest,name
    assert sha(FREEZE)==r['reference_freeze_sha256'] and sha('results/v3/v6full1_analysis_r1_registration.json')==r['analysis_registration_sha256']
    input_registration=Path(r['input_registration_path']);assert sha(input_registration)==r['input_registration_sha256']
    proof_path=input_registration.with_suffix('.result.json');proof=json.loads(proof_path.read_text())
    validate_input_result(proof,r['input_registration_sha256'],json.loads(FREEZE.read_text()))
    manifest=prepare(r['namespace'],FREEZE,analysis_r1=True)
    controller=Path('scripts/reproductions')/r['namespace']/'v6_full.py'
    cli=subprocess.run([sys.executable,str(controller),'--plan'],check=True,capture_output=True,text=True)
    assert json.loads(cli.stdout)['actions']==manifest['actions'] and len(manifest['actions'])==30
    manifest_path=controller.parent/'namespace_manifest.json'
    result=dict(complete_namespace_preparation=True,gpu_execution=False,source_input_reproduction_sha256=sha(proof_path),
        registration_sha256=sha(path),namespace_manifest_path=str(manifest_path),namespace_manifest_sha256=sha(manifest_path),
        generated_cli_plan_equal=True,planned_fresh_arms=30,planned_measured_requests=sum(s['requests'] for s in manifest['actions']),
        scope='Actual verified source/protocol namespace copies and generated CLI plan only. Every future serving arm is fresh; no oldinvalidmarker exception. Independent model outputs/performance and a newnamespacefullseal/GPU study remain unexecuted.')
    with result_path.open('x') as output:output.write(json.dumps(result,indent=2)+'\n')
    print('Prepared fresh R1 namespace',r['namespace'],'GPU execution false',flush=True)


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('register');a.add_argument('pid',type=int);a.add_argument('output',type=Path);a.add_argument('--namespace',required=True)
    a=sub.add_parser('execute');a.add_argument('registration',type=Path);a=p.parse_args()
    if a.command=='register':register(a.pid,a.output,a.namespace);print('Registered namespace preparation waiter',a.output,flush=True)
    else:
        try:execute(a.registration)
        except Exception as exc:
            with a.registration.with_suffix('.failure.json').open('x') as output:output.write(json.dumps(dict(complete=False,error=repr(exc),scope='Retained namespace-preparation failure; no serving calls or automatic retries'),indent=2)+'\n')
            raise


if __name__=='__main__':main()
