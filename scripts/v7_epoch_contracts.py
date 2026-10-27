"""V7 development configuration proof, derived by explicit source transformation."""
import yaml
import copy
from v6_full_analysis_r1 import scalar_argv


def base_configuration(step,setup,summary,entry,parent,seal,freeze,warm=False):
    sg=step['engine']=='sg';rid=step['run_id'];policy=None if warm and sg else 'fifo' if warm else step['policy']
    count=60;runtime=setup['runtime']
    if not sg:
        setup=copy.deepcopy(setup)
        setup['actual_engine_argv_list']=scalar_argv(setup['actual_engine_argv_list'],{'--max-num-seqs','--max-num-batched-tokens','--kv-cache-memory-bytes'})
    assert summary['requests']==summary['successes']==count and summary['errors']==0
    assert summary['model_revision']==parent['model_revision'] and summary['source_sha256']==parent['source_data_sha256']
    assert summary['prompt_version']=='locomo-qwen-concise-v5' and summary['output_tokens_budget']==96
    assert summary['request_read_timeout_s']==summary['request_pool_timeout_s']==180 and summary['client_keepalive_connections']==0
    assert summary['gpu_kv_bytes']==step['gpu_kv_gib']*2**30
    assert not runtime.get('profile_transfers',False) and not runtime.get('profile',False)
    assert not runtime.get('batch_invariant',False) and not runtime.get('kv_events',False)
    snapshots={}
    for key in ['source_files_sha256','frontend_source_sha256','native_overlay_source_sha256','gateway_source_sha256','v6_source_sha256','v7_source_sha256']:snapshots.update(setup.get(key,{}))
    if sg:
        sc=setup['server_config'];public=setup['public_server_env']
        assert sc['max_total_tokens']==(43680 if step['gpu_kv_gib']==6 else 72816) and sc['hicache_size']==16
        assert sc['enable_hierarchical_cache'] and sc['hicache_write_policy']=='write_through'
        assert sc['hicache_io_backend']=='direct' and sc['attention_backend']=='flashinfer' and sc['schedule_policy']==step['native_policy']
        assert sc['max_running_requests']==16 and sc['chunked_prefill_size']==8192 and sc['page_size']==16
        assert sc['context_length']==32768 and sc['dtype']=='bfloat16'
        assert sc['model_path']==setup['model']['path'] and setup['model']['revision']==parent['model_revision']
        assert not sc['disable_decode_cuda_graph'] and not sc['disable_cuda_graph']
        assert public['CACHEFLOW_SGLANG_TRANSFER_PROFILE']!='1' and public['CACHEFLOW_SG_SAME_BATCH_GUARD']=='1'
        assert public['IN_BATCH_PREFIX_CACHING_CHECK_THRESHOLD']==public['IN_BATCH_PREFIX_CACHING_DEPRIORITIZE_THRESHOLD']=='32'
        assert setup['warmup']==warm and setup['reset_status']==200 and setup['gateway_policy']==policy
        assert runtime['schedule_policy']==step['native_policy'] and runtime['gpu_kv_gib']==step['gpu_kv_gib']
        assert runtime['host_kv_gib']==16 and runtime['same_batch_guard'] and runtime['graphs']
        assert runtime['max_running_requests']==16 and runtime['batch_tokens']==8192
        assert runtime['io_backend']=='direct' and runtime['attention_backend']=='flashinfer'
        assert runtime['inbatch_check_threshold']==runtime['inbatch_deprioritize_threshold']==32
        assert setup['package_versions']==freeze['native_package_versions'] and setup['upstream_source_sha256']==freeze['native_source_sha256']
        required={'scripts/v6_sglang_bench.py','scripts/v6_native_metrics.py','src/cacheflow/v6_replay.py',
            'scripts/sglang_profile_hooks/sitecustomize.py','src/cacheflow/v4_sglang_delayhit.py'}
        required|={'scripts/v7_sglang_bench.py','scripts/v7_gateway_identity.py'}
        if policy:assert 'cacheflow.v7_gateway:create_app' in setup['gateway_runtime_entrypoint']['argv']
    else:
        assert summary['vllm_version']==freeze['main_package_versions']['vllm'] and summary['lmcache_version']==freeze['main_package_versions']['lmcache']
        argv=setup['actual_engine_argv_list'];lmargv=setup['actual_lmcache_argv_list']
        assert int(argv[argv.index('--kv-cache-memory-bytes')+1])==step['gpu_kv_gib']*2**30
        assert int(argv[argv.index('--max-num-seqs')+1])==16 and int(argv[argv.index('--max-num-batched-tokens')+1])==8192
        assert '--enforce-eager' not in argv and any(parent['model_revision'] in x for x in argv)
        assert int(float(lmargv[lmargv.index('--l1-size-gb')+1])*2**30)==freeze['host_payload_bytes']
        assert not runtime['residency_events'] and not runtime['enforce_eager']
        assert runtime['cpu_l1_bytes']==freeze['host_payload_bytes'] and runtime['max_num_seqs']==16
        assert runtime['max_num_batched_tokens']==8192 and runtime['kv_capacity_tokens']==(43664 if step['gpu_kv_gib']==6 else 72800)
        assert 'cacheflow.v7_gateway:create_app' in entry['gateway_argv'] and entry['source_sha256']==freeze['actor_sha256']
        assert not entry['native_probe'] and not entry['upstream_profile'] and entry['warmup']==warm
        required=set(parent['source_sha256'])|set(freeze['actor_sha256'])
    if policy:
        cfg=yaml.safe_load(setup['gateway_config']);before=setup['gateway_before'];after=setup['gateway_after']
        assert cfg['scheduler']['policy']==before['policy']==summary['policy']==policy
        assert cfg['scheduler']['max_inflight']==(64 if warm else step['cap']) and cfg['scheduler']['max_queue']==512
        assert cfg['residency']['max_bypasses']==8 and cfg['residency']['kv_capacity_tokens']==(43664 if step['gpu_kv_gib']==6 else 72800)
        assert not cfg['residency']['enabled']
        assert cfg['upstream']==('http://127.0.0.1:8300' if sg else 'http://127.0.0.1:8000')
        assert cfg['model'].endswith(parent['model_revision'])
        assert cfg['http_read_timeout_s']==before['upstream_read_timeout_s']==180
        assert cfg['upstream_keepalive_connections']==0 and cfg['prepare_in_thread'] and before['prepare_mode']=='thread'
        assert before['active']==before['queue']==before['completed_history_requests']==0
        assert not (before.get('decision_stats') or {}).get('calls',0)
        assert after['active']==after['queue']==0
        required|={'src/cacheflow/gateway.py','src/cacheflow/scheduler.py','src/cacheflow/prefix.py','src/cacheflow/v3_memory_scheduler.py','src/cacheflow/v4_prepare.py',
            'src/cacheflow/v6_gateway.py','src/cacheflow/v6_ready_scheduler.py','scripts/v6_runtime.py','scripts/v6_serve_gateway.sh'}
    else:
        assert setup['gateway_config'] is None and setup['gateway_before'] is None
        assert summary['policy']=='sglang_'+step['native_policy']
    if policy:
        required|={'src/cacheflow/v7_gateway.py','src/cacheflow/v7_epoch_scheduler.py','scripts/v7_gateway_identity.py','scripts/v7_serve_gateway.sh'}
        assert {k:cfg['scheduler'][k] for k in ['block_size','min_shared_tokens','max_wait_ms','store_grace_ms','group_window_ms']}==dict(block_size=256,min_shared_tokens=1024,max_wait_ms=200,store_grace_ms=20,group_window_ms=30)
    expected=parent['source_sha256']|freeze['actor_sha256']
    for name in required:assert snapshots[name]==expected[name],(rid,name)
    for name,digest in snapshots.items():
        if name in expected:assert digest==expected[name],(rid,name)
