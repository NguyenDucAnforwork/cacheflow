import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_reproduce_namespace import TEMPLATES,transformed,verify_transform,plan_from_source,prepare,sha


def test_namespace_ast_proof_rejects_algorithm_or_budget_change():
    source=Path('scripts/v6_full_plan.py').read_text();out=transformed(source,'v6repro_demo')
    before=plan_from_source(source);after=plan_from_source(out)
    assert after==[dict(s,run_id=s['run_id'].replace('v6full1','v6repro_demo')) for s in before]
    bad=out.replace("'packing_reuse'","'fifo'")
    with pytest.raises(AssertionError):verify_transform(source,bad,'v6repro_demo')
    with pytest.raises(AssertionError):transformed(source,'../unsafe')


def test_prepare_preserves_reference_and_rejects_collisions(tmp_path):
    repo=Path.cwd();(tmp_path/'scripts').mkdir();(tmp_path/'docs').mkdir()
    for name in TEMPLATES:(tmp_path/'scripts'/name).write_bytes((repo/'scripts'/name).read_bytes())
    analysis=tmp_path/'scripts/analysis.py';analysis.write_text('score = 1\n')
    (tmp_path/'docs/V6_FULL_PROTOCOL.md').write_bytes((repo/'docs/V6_FULL_PROTOCOL.md').read_bytes())
    reference=tmp_path/'reference.json';reference.write_text(json.dumps(dict(status='frozen_prospective_full_study_not_completion',actions=plan_from_source((tmp_path/'scripts/v6_full_plan.py').read_text()),
        actor_sha256={'scripts/'+name:sha(tmp_path/'scripts'/name) for name in TEMPLATES},analysis_source_sha256={'scripts/analysis.py':sha(analysis)},plan_sha256=sha(tmp_path/'docs/V6_FULL_PROTOCOL.md'))))
    original=reference.read_bytes();manifest=prepare('v6repro_demo',reference,tmp_path)
    assert reference.read_bytes()==original and len(manifest['files'])==8
    assert (tmp_path/'scripts/reproductions/v6repro_demo/namespace_manifest.json').exists()
    for source in (repo/'scripts').glob('*.py'):
        destination=tmp_path/'scripts'/source.name
        if not destination.exists():destination.symlink_to(source)
    result=subprocess.run(['/venv/main/bin/python',str(tmp_path/'scripts/reproductions/v6repro_demo/v6_full.py'),'--plan'],cwd=tmp_path,env=dict(os.environ,PYTHONPATH=str(repo/'src')),capture_output=True,text=True,check=True)
    plan=json.loads(result.stdout);assert len(plan['actions'])==30 and all(s['run_id'].startswith('v6repro_demo-') for s in plan['actions'])
    with pytest.raises(AssertionError):prepare('v6repro_demo',reference,tmp_path)
    analysis.write_text('score = 2\n')
    with pytest.raises(AssertionError):prepare('v6repro_changed_analysis',reference,tmp_path)
    assert not (tmp_path/'scripts/reproductions/v6repro_changed_analysis').exists()
    analysis.write_text('score = 1\n')
    (tmp_path/'scripts/v6_full.py').write_text('changed actor')
    with pytest.raises(AssertionError):prepare('v6repro_other',reference,tmp_path)
    assert not (tmp_path/'scripts/reproductions/v6repro_other').exists()
