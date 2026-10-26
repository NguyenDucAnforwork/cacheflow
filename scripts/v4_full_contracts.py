"""Check intended experimental arm against captured actual configuration."""
import yaml


def audit_configuration(step,setup,freeze):
    kind=step['kind'];arm=step['arm'];runtime=setup['runtime']
    if kind=='sg':
        policy='dfs-weight' if '-dfs-' in step['run_id'] else 'lpm'
        assert runtime['schedule_policy']==policy,'native scheduler arm mismatch'
        assert setup['server_config']['schedule_policy']==policy
        assert runtime['gpu_kv_gib']==(10 if '-g10-' in step['run_id'] else 6)
        expected_gateway={'native':None,'fifo':'fifo','union':'packing_reuse'}[arm]
        assert setup['gateway_policy']==expected_gateway,'captured gateway policy differs from planned arm'
        assert setup['public_server_env']['CACHEFLOW_SG_SAME_BATCH_GUARD']=='1'
        assert setup['public_server_env']['CACHEFLOW_SGLANG_TRANSFER_PROFILE']!='1'
        assert setup['server_config']['hicache_size']==48
        if expected_gateway is None:
            assert setup['gateway_config'] is None and setup['gateway_before'] is None
            assert setup['replay_url']=='http://127.0.0.1:8300'
            return
        assert setup['replay_url']=='http://127.0.0.1:8100'
        assert setup['gateway_reset']['method']=='supervisor_restart'
        expected_cap=64;expected_upstream='http://127.0.0.1:8300'
    else:
        assert kind=='main'
        expected_gateway,expected_cap={'fifo64':('fifo',64),'bundle16':('bundle_wave',16),'union64':('packing_reuse',64)}[arm]
        expected_upstream='http://127.0.0.1:8000'
        assert runtime['max_inflight']==expected_cap
        assert runtime['cpu_l1_bytes']==freeze['host_pool_bytes']['full']
        assert runtime['max_bypasses']==freeze['candidate']['max_bypasses']
    cfg=yaml.safe_load(setup['gateway_config']);scheduler=cfg['scheduler'];state=setup['gateway_before']
    assert scheduler['policy']==state['policy']==expected_gateway,'gateway configuration/health/arm mismatch'
    assert scheduler['max_inflight']==expected_cap and scheduler['max_queue']==512
    assert scheduler['block_size']==256 and scheduler['min_shared_tokens']==1024
    assert cfg['residency']['max_bypasses']==freeze['candidate']['max_bypasses']
    assert cfg['residency']['kv_capacity_tokens']==(72800 if '-g10-' in step['run_id'] else 43664)
    assert cfg['upstream']==expected_upstream and cfg['upstream_keepalive_connections']==0
    assert cfg['prepare_in_thread'] and state['prepare_mode']=='thread'
    assert state['completed_history_requests']==state['active']==state['queue']==0
    assert not (state.get('decision_stats') or {}).get('calls',0)
