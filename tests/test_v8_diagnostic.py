"""Whole-failure accounting and GPU controller cleanup without native imports."""
import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import v8_full_liveness_diagnostic as driver
from v8_diagnostic_capture import check_rows


def fixture_rows():
    rows=[];outputs=[];expected={}
    for rid,status in [('success','ok'),('failed','exception:PoolTimeout')]:
        rows.append(dict(request_id=rid,run_id='test',status=status,prompt_sha256='prompt',input_tokens=10,
            output_hash=hashlib.sha256(b'').hexdigest(),engine_request_id='test-'+rid,scheduled_arrival_ns=1,
            client_send_ns=2,complete_ns=3,output_tokens=0 if status=='ok' else None,server_prompt_tokens=10 if status=='ok' else None,
            http_status=200 if status=='ok' else None,first_token_ns=2 if status=='ok' else None))
        outputs.append(dict(request_id=rid,run_id='test',status=status,output=''))
        expected[rid]=dict(prompt_sha256='prompt',input_tokens=10)
    return rows,outputs,expected


def test_failed_rows_required_and_changed_prompt_or_partial_output_rejected():
    rows,outputs,expected=fixture_rows()
    assert check_rows(rows,outputs,expected,'test')=={'ok':1,'exception:PoolTimeout':1}
    with pytest.raises(AssertionError):check_rows(rows[:1],outputs[:1],expected,'test')
    altered=copy.deepcopy(rows);altered[1]['prompt_sha256']='wrong'
    with pytest.raises(AssertionError):check_rows(altered,outputs,expected,'test')
    altered=copy.deepcopy(outputs);altered[1]['output']='lost partial text'
    with pytest.raises(AssertionError):check_rows(rows,altered,expected,'test')


def test_plan_keeps_full_target_all_three_phases():
    actions=driver.plan();assert len(actions)==6
    assert sum(s['requests'] for s in actions if s['label']=='target')==5958
    assert [s['probe'] for s in actions]==[False,False,True,True,False,False]
    assert len({s['trace'] for s in actions if s['label']=='target'})==1


def prepare_driver(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path);base=tmp_path/'results';base.mkdir()
    monkeypatch.setattr(driver,'BASE',base);monkeypatch.setattr(driver,'REG',base/'registration.json')
    parent=base/'parent.json';parent.write_text('{}');parent.with_suffix('.failure.json').write_text('{}');monkeypatch.setattr(driver,'PARENT',parent)
    configs={name:tmp_path/(name+'.conf') for name in ['cacheflow_v2_gateway','cacheflow_v2_vllm']}
    original={n:f'command={driver.ROOT}/scripts/v2_serve_'+('gateway' if n.endswith('gateway') else 'vllm')+'.sh\nenvironment=PROC_NAME="test"\n' for n in configs}
    for n,p in configs.items():p.write_text(original[n])
    monkeypatch.setattr(driver,'CONFIGS',configs)
    r=dict(after_pid=1,config_original=original,model_artifact_sha256={},input_sha256={},actions=driver.plan())
    driver.REG.write_text(json.dumps(r))
    for name in ['v6full1_input_regeneration_registration','v6full1_r1_namespace_preparation_registration','v7_epoch_cpu_probe_registration','v7_epoch_trace_check_registration']:(base/(name+'.result.json')).write_text('{}')
    Path('.cacheflow-v3-gateway.yaml').write_text('{}')
    monkeypatch.setattr(driver,'wait_parent',lambda r:None);monkeypatch.setattr(driver,'idle',lambda:None);monkeypatch.setattr(driver,'verify_pins',lambda r:None)
    monkeypatch.setattr(driver,'workers_terminal',lambda:None)
    monkeypatch.setattr(driver.psutil,'pid_exists',lambda p:False);monkeypatch.setattr(driver,'service_pid',lambda n:0)
    monkeypatch.setattr(driver.shutil,'disk_usage',lambda p:NS(free=200*1024**2));monkeypatch.setattr(driver.time,'sleep',lambda n:None)
    monkeypatch.setattr(driver.httpx,'get',lambda *a,**k:NS(raise_for_status=lambda:None))
    calls=[]
    monkeypatch.setattr(driver.subprocess,'run',lambda args,**kw:calls.append(args))
    return base,configs,original,calls


def test_target_request_errors_are_retained_without_retry_and_all_configs_restored(monkeypatch,tmp_path):
    base,configs,original,calls=prepare_driver(monkeypatch,tmp_path);seen=[]
    def capture(step,digest):
        seen.append(step['run_id']);return dict(run_id=step['run_id'],errors=0 if step['label']=='warm' else 2)
    monkeypatch.setattr(driver,'capture',capture);monkeypatch.setattr(driver,'probe_coverage',lambda r:dict(native_metadata_coverage_checked=True))
    driver.execute();result=json.loads((base/'v8diag1_terminal.json').read_text())
    assert result['diagnostic_execution_complete'] and len(result['outcomes'])==6 and seen==[s['run_id'] for s in driver.plan()]
    assert all(p.read_text()==original[n] for n,p in configs.items())


def test_warm_failure_prevents_target_but_retains_failure_and_restores_configs(monkeypatch,tmp_path):
    base,configs,original,calls=prepare_driver(monkeypatch,tmp_path)
    monkeypatch.setattr(driver,'capture',lambda step,digest:dict(run_id=step['run_id'],errors=1))
    with pytest.raises(RuntimeError,match='Warmup failure'):driver.execute()
    result=json.loads((base/'v8diag1_terminal.json').read_text())
    assert not result['diagnostic_execution_complete'] and len(result['outcomes'])==1
    assert all(p.read_text()==original[n] for n,p in configs.items())


def test_cleanup_attempts_every_service_and_restores_configs_after_stop_error(monkeypatch,tmp_path):
    base,configs,original,calls=prepare_driver(monkeypatch,tmp_path)
    monkeypatch.setattr(driver,'capture',lambda step,digest:dict(errors=1))
    monkeypatch.setattr(driver,'service_pid',lambda n:123)
    def run(args,**kw):
        calls.append(args)
        if args[:3]==['supervisorctl','stop','cacheflow_v2_vllm']:raise RuntimeError('injected stop failure')
    monkeypatch.setattr(driver.subprocess,'run',run)
    with pytest.raises(RuntimeError,match='injected stop failure'):driver.execute()
    stops=[args[2] for args in calls if args[:2]==['supervisorctl','stop']]
    assert stops==driver.SERVICES
    result=json.loads((base/'v8diag1_terminal.json').read_text());assert result['cleanup_errors']
    assert all(p.read_text()==original[n] for n,p in configs.items())
