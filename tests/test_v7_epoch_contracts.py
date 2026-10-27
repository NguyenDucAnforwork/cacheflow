"""Projected metadata acceptance/rejection, not a new dev or GPU result."""
import copy
import json
import sys
from pathlib import Path
import pytest
import yaml
sys.path.insert(0,str(Path('scripts').resolve()))
from v5_verify import verify
from v6_raw_archive import sha
from v7_epoch_study import EXTRA,source_maps,validate_dev_inputs
from v7_epoch_plan import build_plan
from v7_epoch_contract_source import configuration_source
from v7_epoch_contracts import base_configuration


def projected(engine):
    parent,seal=verify();f=json.loads(Path('results/v3/v6full1_freeze.json').read_text());f['host_payload_bytes']=16000745472
    f['actor_sha256'].update({n:sha(n) for n in EXTRA})
    rid=f'v6full1-{engine}-g6-union64-s901';meta=Path('results/v3/sglang' if engine=='sg' else 'results/v3')
    setup=json.loads((meta/(rid+'.setup.json')).read_text());summary=json.loads(Path('results/v3',rid+'.full_audit_r1.json').read_text())['summary']
    summary.update(requests=60,successes=60,request_read_timeout_s=180,request_pool_timeout_s=180)
    step=dict(engine=engine,run_id='projected-no-gpu',gpu_kv_gib=6,native_policy='lpm',policy='packing_reuse',cap=64)
    cfg=yaml.safe_load(setup['gateway_config']);cfg['http_read_timeout_s']=180;setup['gateway_config']=yaml.safe_dump(cfg)
    setup['gateway_before']['upstream_read_timeout_s']=180
    expected=parent['source_sha256']|f['actor_sha256']
    if engine=='sg':
        setup['runtime']['host_kv_gib']=16;setup['server_config']['hicache_size']=16
        setup['gateway_runtime_entrypoint']['argv']=['uvicorn','cacheflow.v7_gateway:create_app']
        setup['v7_source_sha256']={n:expected[n] for n in ['scripts/v7_sglang_bench.py','scripts/v7_gateway_identity.py','src/cacheflow/v7_gateway.py','src/cacheflow/v7_epoch_scheduler.py','scripts/v7_serve_gateway.sh']}
        entry=None
    else:
        setup['runtime']['cpu_l1_bytes']=16000745472
        argv=setup['actual_lmcache_argv_list'];argv[argv.index('--l1-size-gb')+1]=str(16000745472/2**30)
        setup['source_files_sha256'].update(expected)
        entry=dict(gateway_argv=['uvicorn','cacheflow.v7_gateway:create_app'],source_sha256=f['actor_sha256'],native_probe=False,upstream_profile=False,warmup=False)
    return step,setup,summary,entry,parent,seal,f


def test_contract_source_has_only_the_declared_dev_identity_parser_transform():
    assert Path('scripts/v7_epoch_contracts.py').read_text()==configuration_source(Path('scripts/v6_full_contracts.py').read_text())
    with pytest.raises(AssertionError):configuration_source(Path('scripts/v6_full_contracts.py').read_text().replace('count=60 if warm else 1986','count=1'))


def test_runtime_and_analysis_source_seals_match_the_actual_collector_roots():
    maps=source_maps();captured={str(p) for root in ['src/cacheflow','scripts','configs'] for p in Path(root).rglob('*') if p.is_file() and p.suffix in ['.py','.sh','.yaml','.json']}
    assert set(maps['actor_sha256'])<=captured
    evaluator='data/processed/v2/evaluator/evaluation.py'
    assert evaluator in maps['analysis_source_sha256'] and evaluator not in maps['actor_sha256']
def test_actual_existing_development_input_labels_and_nonarrival_semantics():
    parent,_=verify();digest=validate_dev_inputs(build_plan(),parent)
    assert len(digest)==64


@pytest.mark.parametrize('engine',['main','sg'])
def test_projected_same_policy_metadata_and_transport_rejections(engine):
    args=projected(engine);base_configuration(*args)
    for key,value in [('requests',1986),('request_read_timeout_s',3600),('gpu_kv_bytes',10*2**30),('policy','fifo')]:
        bad=copy.deepcopy(args);bad[2][key]=value
        with pytest.raises(AssertionError):base_configuration(*bad)
    bad=copy.deepcopy(args);cfg=yaml.safe_load(bad[1]['gateway_config']);cfg['scheduler']['max_queue']=64;bad[1]['gateway_config']=yaml.safe_dump(cfg)
    with pytest.raises(AssertionError):base_configuration(*bad)


def test_native_host_engine_and_v7_collector_source_rejections():
    args=projected('sg')
    for key,value in [('hicache_size',48),('max_total_tokens',72816),('schedule_policy','dfs-weight'),('disable_decode_cuda_graph',True)]:
        bad=copy.deepcopy(args);bad[1]['server_config'][key]=value
        with pytest.raises(AssertionError):base_configuration(*bad)
    bad=copy.deepcopy(args);bad[1]['v7_source_sha256'].pop('scripts/v7_sglang_bench.py')
    with pytest.raises(KeyError):base_configuration(*bad)
    bad=copy.deepcopy(args);bad[1]['gateway_runtime_entrypoint']['argv']=['uvicorn','cacheflow.v6_gateway:create_app']
    with pytest.raises(AssertionError):base_configuration(*bad)


def test_main_last_scalar_value_and_actual_mode_contracts():
    args=projected('main');argv=args[1]['actual_engine_argv_list']
    assert [argv[i+1] for i,x in enumerate(argv) if x=='--max-num-seqs']==['4','16']
    base_configuration(*args)
    bad=copy.deepcopy(args);argv=bad[1]['actual_engine_argv_list'];i=max(i for i,x in enumerate(argv) if x=='--max-num-seqs');argv[i+1]='4'
    with pytest.raises(AssertionError):base_configuration(*bad)
    bad=copy.deepcopy(args);bad[3]['gateway_argv']=['uvicorn','cacheflow.v6_gateway:create_app']
    with pytest.raises(AssertionError):base_configuration(*bad)
