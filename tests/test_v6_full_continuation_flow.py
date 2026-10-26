"""CPU-only controller lifecycle tests; no real serving or benchmark evidence."""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
import yaml
sys.path.insert(0,str(Path('scripts').resolve()))
import v6_continue_full_r1 as module


def harness(tmp_path,monkeypatch,engine='main',fail_measured=False):
    monkeypatch.chdir(tmp_path);(tmp_path/'results/v3/sglang').mkdir(parents=True);(tmp_path/'results/v3/raw').mkdir()
    config=tmp_path/'gateway.conf';original=f'command={tmp_path}/scripts/v2_serve_gateway.sh\n';config.write_text(original)
    monkeypatch.setattr(module,'CONFIG',config);monkeypatch.setattr(module,'ROOT',tmp_path)
    step=dict(run_id='cpu-test',engine=engine,budget=6,policy='packing_ready',cap=64,trace='cpu-only.jsonl',requests=1986,native_policy='lpm')
    freeze=dict(actions=[step],actor_sha256={'cpu-test':'hash'},host_payload_bytes=48002236416)
    monkeypatch.setattr(module,'verify_continuation',lambda:None);monkeypatch.setattr(module,'remaining_steps',lambda:[step]);monkeypatch.setattr(module,'retained_outcome',lambda:dict(run_id='retained-first',complete=True));monkeypatch.setattr(module,'verify_full',lambda:({}, {},freeze));monkeypatch.setattr(module,'sha',lambda _:'test-hash')
    monkeypatch.setattr(module.shutil,'disk_usage',lambda _:SimpleNamespace(free=1024**3))
    pids={name:0 for name in module.SERVICES};events=[]
    monkeypatch.setattr(module,'service_pid',lambda name:pids[name])
    monkeypatch.setattr(module.psutil,'Process',lambda pid:SimpleNamespace(pid=pid,cmdline=lambda:['uvicorn','cacheflow.v6_gateway:create_app'],environ=lambda:{}))
    monkeypatch.setattr(module.httpx,'get',lambda *a,**k:SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'test':'host-status'}))
    monkeypatch.setattr(module,'capture',lambda *a,**k:{'test':'boundary'})
    monkeypatch.setattr(module,'summarize',lambda *a,**k:dict(coverage_valid=False,coverage_failures=['CPU-only test has no engine histogram']))
    def run(cmd,**kwargs):
        cmd=list(map(str,cmd));events.append(cmd)
        if len(cmd)>1 and cmd[1]=='scripts/v6_runtime.py':
            path=Path('.cacheflow-v3-gateway.yaml');cfg=yaml.safe_load(path.read_text()) if path.exists() else {}
            cfg.update(test_args=cmd[2:]);path.write_text(yaml.safe_dump(cfg))
        elif cmd[:2]==['bash','scripts/v2_start.sh']:
            pids.update(cacheflow_v2_gateway=100,cacheflow_v2_vllm=200,cacheflow_v2_lmcache=300)
        elif cmd[0]=='supervisorctl' and cmd[1] in {'start','restart','stop'}:
            for name in cmd[2:]:pids[name]=0 if cmd[1]=='stop' else 100
        elif cmd[:2]==['bash','scripts/v6_run.sh']:
            rid=cmd[2]
            if fail_measured and not rid.endswith('-warm'):raise subprocess.CalledProcessError(1,cmd)
            raw=Path('results/v3/raw');(raw/(rid+'.summary.json')).write_text(json.dumps(dict(requests=60 if rid.endswith('-warm') else 1986,successes=60 if rid.endswith('-warm') else 1986,errors=0)))
            (raw/(rid+'.jsonl')).write_text(json.dumps(dict(status='cpu-test-only'))+'\n')
        elif len(cmd)>1 and cmd[1]=='scripts/v6_sglang_bench.py':
            if fail_measured and '--warmup' not in cmd:raise subprocess.CalledProcessError(1,cmd)
        elif len(cmd)>1 and cmd[1]=='scripts/v6_audit_full_run_r1.py':
            Path('results/v3/cpu-test.full_audit_r1.json').write_text('{"test_only":true}')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module.subprocess,'run',run)
    def archive(auditpath,archivepath):
        assert Path(auditpath).exists()
        assert any(len(c)>1 and c[1]=='scripts/v6_audit_full_run_r1.py' for c in events)
        assert not any(pids.values()),'Do not archive while serving writers remain live'
        events.append(['archive',str(auditpath)]);Path(archivepath).write_text('{"test_only":true}')
    monkeypatch.setattr(module,'archive',archive);monkeypatch.setattr(sys,'argv',['v6_full.py'])
    return config,original,pids,events


@pytest.mark.parametrize('engine',['main','sg'])
def test_full_controller_orders_warm_measure_audit_archive_and_restores(tmp_path,monkeypatch,engine):
    config,original,pids,events=harness(tmp_path,monkeypatch,engine)
    module.main();assert config.read_text()==original and not any(pids.values())
    outcomes=json.loads(Path('results/v3/v6full1_continuation_r1_outcomes.json').read_text())['runs']
    assert [r['run_id'] for r in outcomes]==['retained-first','cpu-test']
    if engine=='main':
        runs=[c for c in events if c[:2]==['bash','scripts/v6_run.sh']];assert [c[2] for c in runs]==['cpu-test-warm','cpu-test']
        assert sum(c[:2]==['bash','scripts/v2_reset.sh'] for c in events)==2
    else:
        runs=[c for c in events if len(c)>1 and c[1]=='scripts/v6_sglang_bench.py'];assert '--warmup' in runs[0] and '--warmup' not in runs[1]
    archive_index=next(i for i,c in enumerate(events) if c[0]=='archive')
    audit_index=next(i for i,c in enumerate(events) if len(c)>1 and c[1]=='scripts/v6_audit_full_run_r1.py')
    assert audit_index<archive_index
    assert json.loads(Path('results/v3/v6full1_continuation_r1_outcomes.json').read_text())['runs'][0]['complete']


@pytest.mark.parametrize('engine',['main','sg'])
def test_full_controller_retains_failure_without_archive_or_retry(tmp_path,monkeypatch,engine):
    config,original,pids,events=harness(tmp_path,monkeypatch,engine,True)
    with pytest.raises(subprocess.CalledProcessError):module.main()
    assert config.read_text()==original and not any(pids.values())
    assert not any(c[0]=='archive' or (len(c)>1 and c[1]=='scripts/v6_audit_full_run_r1.py') for c in events)
    interruption=json.loads(Path('results/v3/v6full1_continuation_r1_interruption.json').read_text());assert interruption['phase']=='measured' and interruption['completed_arms']==1
    assert not Path('results/v3/v6full1_continuation_r1_outcomes.json').exists()


def test_cleanup_attempts_remaining_services_and_restores_config_after_stop_failure(tmp_path,monkeypatch):
    config,original,pids,events=harness(tmp_path,monkeypatch)
    original_run=module.subprocess.run
    failed_stops=[]
    def fail_stop(cmd,**kwargs):
        if list(cmd)==['supervisorctl','stop','cacheflow_v2_gateway']:
            failed_stops.append(list(cmd))
            raise subprocess.CalledProcessError(1,cmd)
        return original_run(cmd,**kwargs)
    monkeypatch.setattr(module.subprocess,'run',fail_stop)
    with pytest.raises(RuntimeError,match='Failed to stop serving services'):module.main()
    assert failed_stops and config.read_text()==original
    assert pids['cacheflow_v2_vllm']==pids['cacheflow_v2_lmcache']==0
    assert pids['cacheflow_v2_gateway']!=0,'Fixture stop failure must remain visible'
    assert not any(c[0]=='archive' or (len(c)>1 and c[1]=='scripts/v6_audit_full_run_r1.py') for c in events)
    interruption=json.loads(Path('results/v3/v6full1_continuation_r1_interruption.json').read_text())
    assert interruption['phase']=='measured' and 'Failed to stop' in interruption['error']
    assert Path('results/v3/cpu-test.invalid').exists()
    assert interruption['completed_arms']==1 and not Path('results/v3/v6full1_continuation_r1_outcomes.json').exists()


def test_serving_measurement_and_cleanup_functions_are_byte_equivalent_ast():
    import ast
    root=Path(__file__).resolve().parents[1]
    trees=[ast.parse((root/name).read_text()) for name in ['scripts/v6_full.py','scripts/v6_continue_full_r1.py']]
    for name in ['stop','wait','runtime','gateway','main_run','sg_run']:
        functions=[next(n for n in ast.walk(t) if isinstance(n,ast.FunctionDef) and n.name==name) for t in trees]
        assert ast.dump(functions[0])==ast.dump(functions[1]),name
    for func in ['runtime','runner']:
        calls=[[ast.dump(n) for n in ast.walk(t) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id==func] for t in trees]
        assert calls[0]==calls[1],func


def test_plan_is_exact_original_suffix_and_process_audit_unchanged():
    import ast
    import inspect
    import v6_audit_full as old
    import v6_audit_full_r1 as new
    from v6_full_plan import build_plan
    assert ast.dump(ast.parse(inspect.getsource(old.fresh_process_units)))==ast.dump(ast.parse(inspect.getsource(new.fresh_process_units)))
    steps=build_plan();assert len(steps[1:])==29 and sum(s['requests'] for s in steps[1:])==57594
    assert steps[0]['run_id']=='v6full1-main-g6-fifo64-s901'
