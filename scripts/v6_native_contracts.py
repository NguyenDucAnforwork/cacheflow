"""Independent native configuration and captured-ledger checks for V6 analyses."""
import hashlib
import json
from pathlib import Path
import yaml


def configuration(step,block,setup,summary,parent,seal,reg,warm=False):
    runtime=setup['runtime'];sc=setup['server_config'];policy=step.get('policy')
    assert summary['requests']==summary['successes']==step['requests'] and not summary['errors']
    assert summary['prompt_version']=='locomo-qwen-concise-v5' and summary['model_revision']==parent['model_revision']
    assert summary['source_sha256']==parent['source_data_sha256'] and summary['output_tokens_budget']==96
    assert summary['request_read_timeout_s']==summary['request_pool_timeout_s']==180 and summary['client_keepalive_connections']==0
    assert setup['warmup']==warm and setup['reset_status']==200 and setup['gateway_policy']==policy
    assert runtime['gpu_kv_gib']==block['budget'] and runtime['schedule_policy']==block['native_policy']
    assert runtime['host_kv_gib']==16 and runtime['same_batch_guard'] and not runtime['profile_transfers']
    assert runtime['graphs'] and runtime['max_running_requests']==16 and runtime['batch_tokens']==8192
    assert runtime['io_backend']=='direct' and runtime['attention_backend']=='flashinfer'
    assert sc['max_total_tokens']==(43680 if block['budget']==6 else 72816) and sc['hicache_size']==16
    assert sc['enable_hierarchical_cache'] and sc['hicache_write_policy']=='write_through'
    assert sc['schedule_policy']==block['native_policy'] and sc['hicache_io_backend']=='direct' and sc['attention_backend']=='flashinfer'
    assert sc['dtype']=='bfloat16' and sc['context_length']==32768 and sc['page_size']==16
    assert sc['max_running_requests']==16 and sc['chunked_prefill_size']==8192 and not sc['disable_decode_cuda_graph']
    assert sc['model_path']==setup['model']['path'] and setup['model']['revision']==parent['model_revision']
    assert setup['package_versions']==reg['package_versions'] and setup['upstream_source_sha256']==reg['upstream_source_sha256']
    env=setup['public_server_env'];assert env['CACHEFLOW_SGLANG_TRANSFER_PROFILE']!='1' and env['CACHEFLOW_SG_SAME_BATCH_GUARD']=='1'
    assert env['IN_BATCH_PREFIX_CACHING_CHECK_THRESHOLD']==env['IN_BATCH_PREFIX_CACHING_DEPRIORITIZE_THRESHOLD']=='32'
    snapshots={}
    for key in ['frontend_source_sha256','native_overlay_source_sha256','gateway_source_sha256','v6_source_sha256']:snapshots.update(setup.get(key,{}))
    required={'scripts/v6_sglang_bench.py','scripts/v6_native_metrics.py','src/cacheflow/v6_replay.py','scripts/sglang_profile_hooks/sitecustomize.py','src/cacheflow/v4_sglang_delayhit.py'}
    if policy:
        cfg=yaml.safe_load(setup['gateway_config']);before=setup['gateway_before'];after=setup['gateway_after']
        assert cfg['scheduler']['policy']==before['policy']==summary['policy']==policy
        assert cfg['scheduler']['max_inflight']==cfg['scheduler']['max_queue']==64
        assert cfg['residency']['max_bypasses']==8 and cfg['residency']['kv_capacity_tokens']==(43664 if block['budget']==6 else 72800)
        assert not cfg['residency']['enabled'] and cfg['upstream']=='http://127.0.0.1:8300'
        assert cfg['http_read_timeout_s']==before['upstream_read_timeout_s']==180 and cfg['upstream_keepalive_connections']==0
        assert cfg['prepare_in_thread'] and before['prepare_mode']=='thread'
        assert before['active']==before['queue']==before['completed_history_requests']==0
        assert not (before.get('decision_stats') or {}).get('calls',0)
        assert after['active']==after['queue']==0 and 'cacheflow.v6_gateway:create_app' in setup['gateway_runtime_entrypoint']['argv']
        required|={'src/cacheflow/v6_gateway.py','src/cacheflow/v6_ready_scheduler.py','scripts/v6_runtime.py','scripts/v6_serve_gateway.sh'}
    else:assert setup['gateway_config'] is None and setup['gateway_before'] is None and summary['policy']=='sglang_'+block['native_policy']
    expected=parent['source_sha256']|reg['source_sha256']
    for name in required:assert snapshots[name]==expected[name],name
    for name,digest in snapshots.items():
        if name in expected:assert digest==expected[name],name


def ledger(run_id,raw,expected_requests):
    raw=Path(raw);summary=json.loads((raw/(run_id+'.summary.json')).read_text())
    rows=[json.loads(l) for l in (raw/(run_id+'.jsonl')).read_text().splitlines()]
    outputs=[json.loads(l) for l in (raw/(run_id+'.outputs.jsonl')).read_text().splitlines()]
    by={r['request_id']:r for r in rows};texts={r['request_id']:r for r in outputs}
    assert len(by)==len(rows)==len(outputs)==len(texts)==expected_requests==summary['successes']==summary['requests'] and not summary['errors']
    assert by.keys()==texts.keys()
    assert all(r['status']=='ok' and r['run_id']==run_id and r['server_prompt_tokens']==r['input_tokens'] and 0<r['output_tokens']<=96 for r in rows)
    assert all(hashlib.sha256(texts[k]['output'].encode()).hexdigest()==by[k]['output_hash'] for k in by)
    return summary,rows
