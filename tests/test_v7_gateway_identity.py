"""Reject wrong/stale runtime identity and changed gateway process boundaries."""
import copy
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import v7_gateway_identity as module
from v7_collector_source import native_source


def record():
    return dict(implementation='epoch',policy='packing_reuse',
        scheduler_class='cacheflow.v7_epoch_scheduler.EpochUnionScheduler',
        selector='cacheflow.v3_memory_scheduler.ResidencyScheduler._choose_impl',
        source_sha256={str((module.ROOT/name).resolve()):module.sha(module.ROOT/name) for name in module.SOURCES})


@pytest.mark.parametrize('key,value',[
    ('implementation','reference'),('policy','packing_ready'),
    ('scheduler_class','cacheflow.v3_memory_scheduler.ResidencyScheduler'),
    ('selector','cacheflow.v3_memory_scheduler.ResidencyScheduler._choose'),('source_sha256',{})])
def test_config_label_cannot_substitute_for_the_actual_epoch_constructor(key,value):
    good=record();module.validate_identity(good,'packing_reuse','epoch')
    bad=copy.deepcopy(good);bad[key]=value
    with pytest.raises(AssertionError):module.validate_identity(bad,'packing_reuse','epoch')


def boundaries():
    before=dict(gateway_pid=123,gateway_create_time=100.,gateway_argv=['uvicorn','cacheflow.v7_gateway:create_app'],
        implementation_record=record(),observer_source_sha256=module.sha(module.__file__),
        start_ns=10,end_ns=20,health=dict(policy='packing_reuse',active=0,queue=0,completed_history_requests=0,decision_stats=dict(calls=0,cache_hits=0,cache_key_kind='lifecycle_epoch_prototype')))
    after=copy.deepcopy(before);after.update(start_ns=100,end_ns=110);after['health']['decision_stats'].update(calls=10,cache_hits=4)
    after['health']['completed_history_requests']=4
    return before,after


@pytest.mark.parametrize('change',['pid','birth','argv','observer','time','busy','history','fresh_calls','startup_source','same_wrong_observer','health_policy','wrong_cache_kind'])
def test_changed_or_nonfresh_process_boundaries_do_not_pass(change):
    before,after=boundaries();module.validate_pair(before,after)
    if change=='pid':after['gateway_pid']+=1
    elif change=='birth':after['gateway_create_time']+=1
    elif change=='argv':after['gateway_argv']=['uvicorn','cacheflow.v6_gateway:create_app']
    elif change=='observer':after['observer_source_sha256']='changed'
    elif change=='time':after['start_ns']=19
    elif change=='busy':after['health']['active']=1
    elif change=='history':before['health']['completed_history_requests']=1
    elif change=='fresh_calls':before['health']['decision_stats']['calls']=1
    elif change=='same_wrong_observer':
        for row in [before,after]:row['observer_source_sha256']='changed'
    elif change=='health_policy':after['health']['policy']='packing_ready'
    elif change=='wrong_cache_kind':after['health']['decision_stats']['cache_key_kind']='reference'
    else:
        for row in [before,after]:row['implementation_record']['source_sha256']={}
    with pytest.raises(AssertionError):module.validate_pair(before,after)


def test_native_collector_changes_only_the_listed_identity_and_argument_blocks():
    parent=Path('scripts/v6_sglang_bench.py').read_text()
    assert Path('scripts/v7_sglang_bench.py').read_text()==native_source(parent)
    with pytest.raises(AssertionError):native_source(parent.replace('cacheflow.v6_gateway:create_app','unexpected_factory'))


@pytest.mark.parametrize('bad',['empty','late_before','early_after'])
def test_identity_capture_must_bracket_the_actual_request_window(bad):
    before,after=boundaries();rows=[dict(scheduled_arrival_ns=30,complete_ns=90)]
    module.validate_replay_window(before,after,rows)
    if bad=='empty':rows=[]
    elif bad=='late_before':before['end_ns']=31
    else:after['start_ns']=89
    with pytest.raises(AssertionError):module.validate_replay_window(before,after,rows)


def test_main_wrapper_preserves_original_capture_and_explicit_boundary_gates():
    import subprocess
    subprocess.run(['bash','-n','scripts/v7_run.sh'],check=True)
    text=Path('scripts/v7_run.sh').read_text()
    assert 'bash scripts/v6_run.sh "$id" "$trace" "$url"' in text
    assert '--fresh --output "$before"' in text and 'verify-pair "$before" "$after"' in text
    assert '[[ ! -e "results/v3/$id.invalid" ]]' in text
