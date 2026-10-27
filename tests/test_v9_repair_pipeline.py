import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import v9_repair as driver
from v9_repair_capture import capture_source
import v4_services


def test_fixed_full_scope_and_reversed_second_seed():
    p=driver.plan();assert len(p)==6 and sum(s['requests'] for s in p)==8064
    assert [s['mode'] for s in p[2:]]==['reference','idempotent','idempotent','reference']
    assert [s['seed'] for s in p[2:]]==[901,901,902,902]
    assert all(not s['probe'] and s['requests']==1986 for s in p[2:])
    assert all(s['probe'] and s['requests']==60 for s in p[:2])


def test_capture_transform_preserves_request_replay_body():
    source,proof=capture_source();text=Path('scripts/v8_diagnostic_capture.py').read_text()
    assert "BASE/'v9repair1_registry.csv'" in source
    for change in reversed(proof['changes']):
        assert source.count(change['new'])==1;source=source.replace(change['new'],change['old'],1)
    fn=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='capture')
    assert source==ast.get_source_segment(text,fn)


def test_stop_attempts_every_service_even_after_one_failure(monkeypatch):
    monkeypatch.setattr(v4_services,'service_pid',lambda n:123);seen=[]
    def call(*args):
        seen.append(args[-1])
        if args[-1]=='cacheflow_v2_vllm':raise RuntimeError('stop failed')
    with pytest.raises(RuntimeError,match='stop failed'):driver.stop_services(call)
    assert seen==driver.SERVICES


@pytest.mark.parametrize('stored,inflated',[(2048,1),(1024,0)])
def test_probe_gate_has_real_eligible_samples_and_detects_inflation(monkeypatch,tmp_path,stored,inflated):
    monkeypatch.setattr(driver,'BASE',tmp_path);raw=tmp_path/'raw';raw.mkdir();rows=[]
    for target in ['scheduler','allocator','connector','worker']:rows.append(dict(kind='hook_ready',target=target,source_path='native.py',source_sha256='sha'))
    rows.extend([dict(kind='scheduler'),dict(kind='connector_worker'),dict(kind='connector_metadata',pid=7,monotonic_ns=1,tracker_states={'r':dict(state='PREFETCHING',num_scheduled_tokens=0,allocated_blocks_per_group={},lmcache_hit_tokens=1024,num_stored_tokens=stored)})])
    path=raw/'proof.7.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    result=driver.probe_audit(dict(probe_label='proof'),dict(native_source_sha256={'native.py':'sha'}))
    assert result['eligible_sampled_prefetch_states']==1 and result['distinct_inflated_ids']==inflated
    rows.append(dict(kind='probe_error'));path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    with pytest.raises(AssertionError):driver.probe_audit(dict(probe_label='proof'),dict(native_source_sha256={'native.py':'sha'}))


def setup_driver(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path);base=tmp_path/'results';base.mkdir();monkeypatch.setattr(driver,'BASE',base);monkeypatch.setattr(driver,'REG',base/'reg.json')
    terminal=base/'v8diag3_terminal.json';terminal.write_text(json.dumps(dict(diagnostic_execution_complete=True,cleanup_errors=[],outcomes=[{}]*4)))
    configs={n:tmp_path/(n+'.conf') for n in ['cacheflow_v2_vllm','cacheflow_v2_gateway']}
    original={n:f'command={tmp_path}/scripts/v2_serve_'+('vllm' if n.endswith('vllm') else 'gateway')+'.sh\nenvironment=PROC_NAME="test"\n' for n in configs}
    for n,path in configs.items():path.write_text(original[n])
    monkeypatch.setattr(driver,'CONFIGS',configs)
    r=dict(wait_mode='already_terminal_verified_process_scan',terminal_sha256=driver.sha(terminal),config_original=original,
        actions=driver.plan()[:1],native_source_sha256={str(driver.SOURCE):'sha'})
    driver.REG.write_text(json.dumps(r));Path('.cacheflow-v3-gateway.yaml').write_text('{}')
    monkeypatch.setattr(driver,'original_terminal',lambda:None);monkeypatch.setattr(driver,'idle_gpu',lambda:None);monkeypatch.setattr(driver,'verify',lambda *a,**kw:None)
    monkeypatch.setattr(driver.shutil,'disk_usage',lambda p:NS(free=200*1024**2))
    monkeypatch.setattr(v4_services,'service_pid',lambda n:0)
    return base,configs,original


def test_configuration_failure_restores_both_configs_and_retains_terminal_error(monkeypatch,tmp_path):
    base,configs,original=setup_driver(monkeypatch,tmp_path)
    def run(args,**kwargs):
        if 'scripts/v6_runtime.py' in args:raise RuntimeError('runtime injection')
    monkeypatch.setattr(driver.subprocess,'run',run)
    with pytest.raises(RuntimeError,match='runtime injection'):driver.execute()
    result=json.loads((base/'v9repair1_terminal.json').read_text());assert result['diagnostic_execution_complete'] is False and result['cleanup_errors']==[]
    assert result['outcomes']==[] and all(p.read_text()==original[n] for n,p in configs.items())


def test_failed_warmup_never_replays_target_and_restores_configs(monkeypatch,tmp_path):
    base,configs,original=setup_driver(monkeypatch,tmp_path);seen=[]
    monkeypatch.setattr(driver.subprocess,'run',lambda *a,**kw:None)
    monkeypatch.setattr(driver.httpx,'get',lambda *a,**kw:NS(raise_for_status=lambda:None,json=lambda:dict(storage_manager={'l1_manager':{'memory_total_bytes':48049946624}})))
    def capture(step,registration):seen.append(step['run_id']);return dict(errors=1)
    monkeypatch.setattr(driver,'capture',capture)
    with pytest.raises(RuntimeError,match='Warmup failure'):driver.execute()
    assert seen==[driver.plan()[0]['run_id']+'-warm'] and all(p.read_text()==original[n] for n,p in configs.items())
