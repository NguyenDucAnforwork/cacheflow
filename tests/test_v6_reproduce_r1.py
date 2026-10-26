"""Namespace/analysis proofs only; projected seals are not new GPU results."""
import ast
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
import yaml
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_reproduce_namespace import TEMPLATES,prepare,sha,plan_from_source,scalar_definition,r1_contract,verify_r1_transform
from v5_verify import verify


def fixture(tmp_path):
    root=Path.cwd();(tmp_path/'scripts').mkdir();(tmp_path/'docs').mkdir();(tmp_path/'results/v3').mkdir(parents=True)
    for name in TEMPLATES:(tmp_path/'scripts'/name).write_bytes((root/'scripts'/name).read_bytes())
    helper=tmp_path/'scripts/v6_full_analysis_r1.py';helper.write_bytes((root/'scripts/v6_full_analysis_r1.py').read_bytes())
    doc=tmp_path/'docs/V6_FULL_PROTOCOL.md';doc.write_bytes((root/'docs/V6_FULL_PROTOCOL.md').read_bytes())
    reference=tmp_path/'reference.json';reference.write_text(json.dumps(dict(status='frozen_prospective_full_study_not_completion',
        actions=plan_from_source((tmp_path/'scripts/v6_full_plan.py').read_text()),actor_sha256={'scripts/'+n:sha(tmp_path/'scripts'/n) for n in TEMPLATES},plan_sha256=sha(doc))))
    proof=copy.deepcopy(json.loads((root/'results/v3/v6full1_analysis_r1_registration.json').read_text()))
    # This fixture is a projected lineage record, not a second observed parser proof.
    proof['reference_freeze_sha256']=sha(reference)
    path=tmp_path/'results/v3/v6full1_analysis_r1_registration.json';path.write_text(json.dumps(proof))
    return root,reference,path


def test_r1_transform_cannot_change_budget_policy_or_helper():
    original=Path('scripts/v6_full_contracts.py').read_text();normalizer=scalar_definition(Path.cwd())
    output=r1_contract(original,'v6repro_r1_test',normalizer)
    verify_r1_transform(original,output,'v6repro_r1_test',normalizer)
    for before,after in [('==8192','==4096'),("'--max-num-seqs'","'--wrong-option'"),('found[key] = value','found[key] = "16"')]:
        assert before in output
        with pytest.raises(AssertionError):verify_r1_transform(original,output.replace(before,after),'v6repro_r1_test',normalizer)
    assert 'validate_retained_audit_interruption' not in output


def test_generated_contract_accepts_actual_last_value_and_rejects_wrong_override():
    original=Path('scripts/v6_full_contracts.py').read_text();out=r1_contract(original,'v6repro_r1_test',scalar_definition(Path.cwd()))
    nodes=[n for n in ast.parse(out).body if isinstance(n,ast.FunctionDef)]
    scope={'yaml':yaml};exec(compile(ast.Module(body=nodes,type_ignores=[]),'generated_contract_fixture','exec'),scope)
    parent,seal=verify();freeze=json.loads(Path('results/v3/v6full1_freeze.json').read_text());step=freeze['actions'][0]
    # Metadata is real captured data; this exercise creates no new engine or ledger.
    setup=json.loads(Path('results/v3/v6full1-main-g6-fifo64-s901.setup.json').read_text())
    audit=json.loads(Path('results/v3/v6full1-main-g6-fifo64-s901.full_audit_r1.json').read_text())
    entry=json.loads(Path('results/v3/v6full1-main-g6-fifo64-s901.v6_entrypoint.json').read_text())
    args=[step,setup,audit['summary'],entry,parent,seal,freeze]
    scope['audit_configuration'](*args)
    setup['actual_engine_argv_list'].extend(['--max-num-seqs','4'])
    with pytest.raises(AssertionError):scope['audit_configuration'](*args)


def test_r1_namespace_cli_preserves_all30_fresh_actions(tmp_path):
    root,reference,proof=fixture(tmp_path);before=reference.read_bytes()
    manifest=prepare('v6repro_r1_test',reference,tmp_path,analysis_r1=True)
    assert reference.read_bytes()==before and len(manifest['files'])==8
    assert manifest['analysis_revision']['reference_registration_sha256']==sha(proof)
    assert len(manifest['actions'])==30 and all(s['run_id'].startswith('v6repro_r1_test-') for s in manifest['actions'])
    for source in (root/'scripts').glob('*.py'):
        target=tmp_path/'scripts'/source.name
        if not target.exists():target.symlink_to(source)
    bundle=tmp_path/'scripts/reproductions/v6repro_r1_test'
    env=dict(os.environ,PYTHONPATH=str(root/'src'))
    cli=subprocess.run(['/venv/main/bin/python',str(bundle/'v6_full.py'),'--plan'],cwd=tmp_path,env=env,capture_output=True,text=True,check=True)
    assert json.loads(cli.stdout)['actions']==manifest['actions']
    subprocess.run(['/venv/main/bin/python',str(bundle/'v6_audit_full_run.py'),'--help'],cwd=tmp_path,env=env,capture_output=True,text=True,check=True)
    with pytest.raises(AssertionError):prepare('v6repro_r1_test',reference,tmp_path,analysis_r1=True)


def test_changed_scalar_lineage_is_rejected_before_namespace_creation(tmp_path):
    root,reference,proof=fixture(tmp_path)
    data=json.loads(proof.read_text());data['parser_proof'][0]['installed_parser_max_num_seqs']=4;proof.write_text(json.dumps(data))
    with pytest.raises(AssertionError):prepare('v6repro_wrong_parser',reference,tmp_path,analysis_r1=True)
    assert not (tmp_path/'scripts/reproductions/v6repro_wrong_parser').exists()
    data['parser_proof'][0]['installed_parser_max_num_seqs']=16;proof.write_text(json.dumps(data))
    (tmp_path/'scripts/v6_full_analysis_r1.py').write_text('def scalar_argv(*args): return []\n')
    with pytest.raises(AssertionError):prepare('v6repro_wrong_helper',reference,tmp_path,analysis_r1=True)
    assert not (tmp_path/'scripts/reproductions/v6repro_wrong_helper').exists()
