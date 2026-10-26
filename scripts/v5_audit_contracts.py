"""Shared V5 evidence contract: actual transport, arm, budget and source coverage."""
import yaml
from cacheflow.v4_resources import sglang_host_pool_bytes


def audit_common(step,setup,summary,manifest,parent,seal):
    rid=step['run_id'];kind=step['kind'];full='-full-' in rid
    assert summary['run_id']==rid and summary['requests']==summary['successes']==manifest['requests'] and not summary['errors']
    assert summary['prompt_version']==manifest['prompt_version']=='locomo-qwen-concise-v5'
    assert summary['trace_sha256']==manifest['trace_sha256']
    assert manifest['parent_method_freeze_sha256']==seal['parent_method_freeze_sha256']
    assert manifest['renderer_sha256']==seal['source_sha256']['src/cacheflow/v5_prompt.py']
    assert manifest['abstention_style']=='official_consistent_system_and_user'
    assert summary['model_revision']==parent['model_revision'] and summary['source_sha256']==parent['source_data_sha256']
    assert summary['output_tokens_budget']==96
    assert summary['client_keepalive_connections']==0
    assert summary['request_read_timeout_s']==summary['request_pool_timeout_s']==3600
    snapshots={}
    for key in ['source_files_sha256','frontend_source_sha256','native_overlay_source_sha256','gateway_source_sha256']:
        snapshots.update(setup.get(key,{}))
    runtime=setup['runtime'];gateway=setup.get('gateway_config')
    if kind=='main':
        required=set(parent['source_sha256'])
        expected,cap={'fifo16':('fifo',16),'fifo64':('fifo',64),'lpm16':('lpm_real',16),
            'bundle16':('bundle_wave',16),'dhas16':('dhas',16),'union64':('packing_reuse',64)}[step['arm']]
        budget=parent['host_pool_bytes']['full' if full else 'dev_and_confirmation']
        assert runtime['cpu_l1_bytes']==budget
        argv=setup['actual_lmcache_argv_list'];assert int(float(argv[argv.index('--l1-size-gb')+1])*2**30)==budget
        assert bool(runtime['residency_events'])==bool(not full)
    else:
        assert kind=='sg'
        required={'scripts/v3_sglang_bench.py','src/cacheflow/v2_replay.py',
            'scripts/sglang_profile_hooks/sitecustomize.py','src/cacheflow/v4_sglang_delayhit.py'}
        expected={'native':None,'fifo':'fifo','union':'packing_reuse'}[step['arm']];cap=64
        assert setup['gateway_policy']==expected
        assert runtime['schedule_policy']==('dfs-weight' if '-dfs-' in rid else 'lpm')
        assert runtime['gpu_kv_gib']==(10 if '-g10-' in rid else 6)
        assert runtime['same_batch_guard'] and not runtime['profile_transfers']
        assert runtime['max_running_requests']==16 and runtime['batch_tokens']==8192
        assert runtime['io_backend']=='direct' and runtime['attention_backend']=='flashinfer'
        assert setup['reset_status']==200
        assert sglang_host_pool_bytes(runtime['host_kv_gib'],147456)==parent['host_pool_bytes']['full' if full else 'dev_and_confirmation']
    if expected:
        assert gateway is not None
        required|={'src/cacheflow/gateway.py','src/cacheflow/scheduler.py','src/cacheflow/prefix.py',
            'src/cacheflow/v3_memory_scheduler.py','src/cacheflow/v4_prepare.py'}
        cfg=yaml.safe_load(gateway);before=setup['gateway_before']
        assert cfg['scheduler']['policy']==before['policy']==expected
        assert cfg['scheduler']['max_inflight']==cap and cfg['scheduler']['max_queue']==(512 if full else 64)
        assert cfg['http_read_timeout_s']==before['upstream_read_timeout_s']==3600
        assert cfg['prepare_in_thread'] and before['prepare_mode']=='thread'
        assert cfg['upstream_keepalive_connections']==0 and cfg['residency']['max_bypasses']==8
        assert before['active']==before['queue']==before['completed_history_requests']==0
        assert not (before.get('decision_stats') or {}).get('calls',0)
    else:
        assert gateway is None and setup['gateway_before'] is None
    assert required<=snapshots.keys(),('missing source-fingerprint evidence',rid,sorted(required-snapshots.keys()))
    for name in required:assert snapshots[name]==parent['source_sha256'][name],('source differs from seal',rid,name)
