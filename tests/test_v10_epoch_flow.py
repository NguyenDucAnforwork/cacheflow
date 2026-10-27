"""CPU fault injection for controller ownership/order/restoration, no inference."""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
import yaml
sys.path.insert(0,str(Path('scripts').resolve()))
import v10_epoch_dev as module


def harness(tmp_path,monkeypatch,engine='main',failure=None):
    monkeypatch.chdir(tmp_path);Path('results/v3/sglang').mkdir(parents=True);Path('results/v3/raw').mkdir()
    config=tmp_path/'gateway.conf';original=f'command={tmp_path}/scripts/v2_serve_gateway.sh\n';config.write_text(original)
    vllm_config=tmp_path/'vllm.conf';vllm_config.write_text('original-vllm')
    monkeypatch.setattr(module,'VLLM_CONFIG',vllm_config)
    monkeypatch.setattr(module,'engine_config',lambda original,step,freeze:original+'-idempotent')
    monkeypatch.setattr(module,'capture_identity',lambda *args:dict(cpu_fixture=True))
    monkeypatch.setattr(module,'validate_identity',lambda *args:True)
    monkeypatch.setattr(module,'CONFIG',config);monkeypatch.setattr(module,'ROOT',tmp_path)
    step=dict(run_id='cpu-fixture',engine=engine,gpu_kv_gib=6,policy='packing_reuse',implementation='epoch',cap=64,trace='cpu-fixture.jsonl',requests=60,native_policy='lpm')
    freeze=dict(actions=[step],actor_sha256={'cpu-only':'hash'},host_payload_bytes=16000745472)
    monkeypatch.setattr(module,'verify',lambda *a,**k:({}, {},freeze));monkeypatch.setattr(module,'sha',lambda _:'hash')
    pids={name:0 for name in module.SERVICES};events=[]
    monkeypatch.setattr(module,'service_pid',lambda name:pids[name])
    monkeypatch.setattr(module.psutil,'Process',lambda pid:SimpleNamespace(pid=pid,cmdline=lambda:['uvicorn','cacheflow.v7_gateway:create_app'],environ=lambda:{}))
    monkeypatch.setattr(module.httpx,'get',lambda *a,**k:SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'cpu_fixture':'not_actual_capacity'}))
    monkeypatch.setattr(module,'capture',lambda *a,**k:dict(cpu_fixture=True))
    monkeypatch.setattr(module,'summarize',lambda *a,**k:dict(coverage_valid=False,scope='CPU fixture, no histogram or performance result'))
    def run(cmd,**kwargs):
        cmd=list(map(str,cmd));events.append(cmd)
        if len(cmd)>1 and cmd[1]=='scripts/v6_runtime.py':
            Path('.cacheflow-v3-gateway.yaml').write_text(yaml.safe_dump(dict(test_arguments=cmd[2:])))
        elif cmd[:2]==['bash','scripts/v2_start.sh']:pids.update(cacheflow_v2_gateway=100,cacheflow_v2_vllm=200,cacheflow_v2_lmcache=300)
        elif cmd[0]=='supervisorctl' and cmd[1] in {'start','restart','stop'}:
            if failure=='stop' and cmd[1:]==['stop','cacheflow_v2_gateway']:raise subprocess.CalledProcessError(1,cmd)
            for name in cmd[2:]:pids[name]=0 if cmd[1]=='stop' else 100
        elif cmd[:2]==['supervisorctl','update'] and failure=='restore' and config.read_text()==original:raise subprocess.CalledProcessError(1,cmd)
        elif cmd[:2]==['bash','scripts/v7_run.sh'] or (len(cmd)>1 and cmd[1]=='scripts/v7_sglang_bench.py'):
            rid=cmd[2]
            if failure=='measured' and not rid.endswith('-warm'):raise subprocess.CalledProcessError(1,cmd)
            if failure=='warmup' and rid.endswith('-warm'):raise subprocess.CalledProcessError(1,cmd)
            if engine=='main':
                raw=Path('results/v3/raw');(raw/(rid+'.summary.json')).write_text(json.dumps(dict(requests=60,successes=60,errors=0)))
                (raw/(rid+'.jsonl')).write_text('{"cpu_fixture":true}\n')
        elif len(cmd)>1 and cmd[1]=='scripts/v10_audit_epoch_run.py':Path('results/v3/cpu-fixture.v10_audit.json').write_text('{"cpu_fixture":true}')
        elif len(cmd)>1 and cmd[1]=='scripts/v10_audit_epoch_dev.py' and failure=='terminal_audit':raise subprocess.CalledProcessError(1,cmd)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module.subprocess,'run',run)
    def archive(ap,zp):
        assert Path(ap).exists() and not any(pids.values()),'Audit first and no live raw writers'
        events.append(['archive',str(ap)])
        if failure=='archive':raise OSError('CPU fixture archive failure')
        Path(zp).write_text('{"cpu_fixture":true}')
    monkeypatch.setattr(module,'archive',archive)
    return config,original,pids,events


@pytest.mark.parametrize('engine',['main','sg'])
def test_orders_warm_measure_audit_archive_then_restores(tmp_path,monkeypatch,engine):
    config,original,pids,events=harness(tmp_path,monkeypatch,engine)
    module.execute();assert module.VLLM_CONFIG.read_text()=='original-vllm'
    assert module.VLLM_CONFIG.read_text()=='original-vllm'
    assert config.read_text()==original and not any(pids.values()) and not module.MARKER.exists()
    replay=[r for r in events if r[:2]==['bash','scripts/v7_run.sh'] or (len(r)>1 and r[1]=='scripts/v7_sglang_bench.py')]
    assert [r[2] for r in replay]==['cpu-fixture-warm','cpu-fixture']
    if engine=='main':assert [r[4] for r in replay]==['reference','epoch']
    else:assert '--warmup' in replay[0] and '--scheduler-implementation' not in replay[0] and replay[1][-1]=='epoch'
    assert next(i for i,r in enumerate(events) if len(r)>1 and r[1]=='scripts/v10_audit_epoch_run.py')<next(i for i,r in enumerate(events) if r[0]=='archive')
    assert json.loads(Path('results/v3/v10dev1_epoch_outcomes.json').read_text())['runs'][0]['complete'] is True


@pytest.mark.parametrize('engine',['main','sg'])
@pytest.mark.parametrize('failure',['warmup','measured','archive'])
def test_failures_are_retained_without_serving_retries(tmp_path,monkeypatch,engine,failure):
    config,original,pids,events=harness(tmp_path,monkeypatch,engine,failure)
    with pytest.raises((subprocess.CalledProcessError,OSError)):module.execute()
    assert module.VLLM_CONFIG.read_text()=='original-vllm'
    assert config.read_text()==original and not any(pids.values()) and not module.MARKER.exists()
    interruption=json.loads(Path('results/v3/v10dev1_epoch_interruption.json').read_text());assert interruption['phase']==failure and interruption['completed_arms']==0
    assert not Path('results/v3/v10dev1_epoch_outcomes.json').exists()
    assert not any(len(r)>1 and r[1]=='scripts/v10_audit_epoch_dev.py' for r in events)


@pytest.mark.parametrize('failure',['stop','restore','terminal_audit'])
def test_cleanup_and_terminal_audit_failures_remain_visible(tmp_path,monkeypatch,failure):
    config,original,pids,events=harness(tmp_path,monkeypatch,failure=failure)
    with pytest.raises((RuntimeError,subprocess.CalledProcessError)):module.execute()
    assert config.read_text()==original and not module.MARKER.exists()
    assert pids['cacheflow_v2_vllm']==pids['cacheflow_v2_lmcache']==0
    d=json.loads(Path('results/v3/v10dev1_epoch_interruption.json').read_text())
    if failure in {'stop','restore'}:assert d['cleanup_errors']
    else:assert d['phase']=='terminal_audit' and d['completed_arms']==1


def test_busy_service_is_not_stopped_or_reconfigured(tmp_path,monkeypatch):
    config,original,pids,events=harness(tmp_path,monkeypatch);pids['cacheflow_v3_sglang']=999
    with pytest.raises(AssertionError,match='idle'):module.execute()
    assert pids['cacheflow_v3_sglang']==999 and config.read_text()==original and not events
    assert not Path('results/v3/v10dev1_epoch_execution.json').exists()
