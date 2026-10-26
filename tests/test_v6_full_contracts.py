"""Mutate captured native evidence to test full-budget/policy/transport rejection.

The projected fixture only tests the verifier. It is not a full GPU execution.
"""
import copy
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_full_contracts import audit_configuration
from v5_verify import verify


def projected():
    parent,seal=verify()
    setup=json.loads(Path('results/v3/sglang/v5r2-dev-lpm-g6-qps4-native-s101.setup.json').read_text())
    setup['runtime']['host_kv_gib']=48;setup['server_config']['hicache_size']=48;setup['warmup']=False
    step=dict(engine='sg',run_id='projected',budget=6,native_policy='lpm',policy=None,cap=64)
    summary=dict(policy='sglang_lpm',requests=1986,successes=1986,errors=0,model_revision=parent['model_revision'],source_sha256=parent['source_data_sha256'],
        prompt_version='locomo-qwen-concise-v5',output_tokens_budget=96,request_read_timeout_s=3600,request_pool_timeout_s=3600,client_keepalive_connections=0,gpu_kv_bytes=6*2**30)
    names=['scripts/v6_sglang_bench.py','scripts/v6_native_metrics.py','src/cacheflow/v6_replay.py']
    extra={n:'projected-source-'+n for n in names};setup['frontend_source_sha256'].update(extra)
    freeze=dict(native_package_versions=setup['package_versions'],native_source_sha256=setup['upstream_source_sha256'],actor_sha256=extra)
    return step,setup,summary,None,parent,seal,freeze


def test_projected_native_configuration_and_mismatch_rejections():
    args=projected();audit_configuration(*args)
    for mutate in [lambda s:s['server_config'].update(hicache_size=16),lambda s:s['server_config'].update(schedule_policy='dfs-weight'),
        lambda s:s['public_server_env'].update(CACHEFLOW_SGLANG_TRANSFER_PROFILE='1'),
        lambda s:s['server_config'].update(max_total_tokens=72816),lambda s:s['runtime'].update(same_batch_guard=False),
        lambda s:s['frontend_source_sha256'].pop('src/cacheflow/v6_replay.py')]:
        changed=copy.deepcopy(args);mutate(changed[1])
        with pytest.raises((AssertionError,KeyError)):audit_configuration(*changed)
    changed=copy.deepcopy(args);changed[2]['request_read_timeout_s']=180
    with pytest.raises(AssertionError):audit_configuration(*changed)
