import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('analyze_e2', Path(__file__).parents[1] / 'scripts/v2_analyze_e2.py')
e2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2)


def arms():
    metadata = dict(trace_sha256='trace', gpu_kv_bytes=4*1024**3, model_revision='rev',
                    model_name='model', max_model_len=32768, output_tokens_budget=64,
                    source_sha256='source', prompt_version='v1', protocol='p_qa',
                    arrival='interleaved', python_version='3.12', vllm_version='0.22',
                    lmcache_version='0.5', transformers_version='5.6', policy='fifo',
                    arrival_ttft_p50_ms=1000, arrival_ttft_p95_ms=2000,
                    arrival_ttft_p99_ms=2100, requests_per_s=.2)
    request = dict(prompt_sha256='prompt', input_tokens=100, server_prompt_tokens=100,
                   sample_id='sample', qa_index=0, arrival_ttft_ms=1000,
                   output_hash='answer', output_tokens=20)
    first = {'summary': dict(metadata, mode='B1', run_id='first'),
             'requests': {'q0': request}, 'metrics': {'counter_deltas': {'vllm': {}, 'lmcache': {}}}}
    second = copy.deepcopy(first)
    second['summary'].update(mode='B2', run_id='second', arrival_ttft_p95_ms=1000)
    return first, second


def test_tiering_comparison_rejects_different_prompts_and_arrivals():
    first, second = arms()
    second['requests']['q0']['prompt_sha256'] = 'different'
    with pytest.raises(ValueError, match='prompt_sha256'):
        e2.compare(first, second)
    first, second = arms()
    second['summary']['trace_sha256'] = 'different arrivals'
    with pytest.raises(ValueError, match='trace_sha256'):
        e2.compare(first, second)


def test_missing_restore_counter_stays_null_and_output_mismatch_is_reported():
    first, second = arms()
    second['requests']['q0']['output_hash'] = 'different answer'
    result = e2.compare(first, second)
    assert result['output_hash_matches'] == 0
    assert result['counters']['loaded_chunks'] == {'b1': None, 'b2': None, 'delta': None}
    assert result['latency']['arrival_ttft_p95_ms']['relative_change_pct'] == -50


def test_interval_uses_run_units_and_exposes_uncertainty():
    result = e2.run_level_interval([-100, 0, 100])
    assert result['n_runs'] == 3 and result['mean'] == 0
    assert result['exploratory_t95_interval'][0] < -200
    assert e2.run_level_interval([1])['exploratory_t95_interval'] is None


def write_run(tmp_path):
    import hashlib
    import json
    raw = tmp_path / 'results/v2/raw'
    raw.mkdir(parents=True)
    summary = dict(run_id='r', requests=1, successes=1, errors=0, trace_sha256='trace', output_tokens_budget=64)
    request = dict(request_id='q', run_id='r', trace_sha256='trace', status='ok',
                   server_prompt_tokens=100, input_tokens=100, output_tokens=1,
                   output_hash=hashlib.sha256(b'answer').hexdigest())
    gateway = dict(request_id='q', run_id='r', input_tokens=100, status='ok')
    output = dict(request_id='q', run_id='r', output='answer', status='ok')
    for suffix, data in [('summary.json', summary), ('jsonl', request), ('gateway.jsonl', gateway),
                         ('outputs.jsonl', output), ('reset_health.json', dict(active=0, queue=0))]:
        (raw / f'r.{suffix}').write_text(json.dumps(data)+'\n')
    metrics = dict(counter_deltas=dict(vllm={'vllm:request_prefill_kv_computed_tokens_sum': 60,
                                           'vllm:prompt_tokens_cached_total': 40}))
    (raw.parent / 'r.metrics_summary.json').write_text(json.dumps(metrics))
    return raw


def test_incomplete_metric_window_and_foreign_output_are_rejected(tmp_path):
    import json
    raw = write_run(tmp_path)
    assert e2.load_run(tmp_path, 'r')['summary']['successes'] == 1
    path = raw.parent / 'r.metrics_summary.json'
    metrics = json.loads(path.read_text())
    metrics['counter_deltas']['vllm']['vllm:prompt_tokens_cached_total'] = 30
    path.write_text(json.dumps(metrics))
    with pytest.raises(ValueError, match='do not account'):
        e2.load_run(tmp_path, 'r')
    output = dict(request_id='q', run_id='different-run', output='answer')
    (raw / 'r.outputs.jsonl').write_text(json.dumps(output)+'\n')
    with pytest.raises(ValueError, match='provenance'):
        e2.load_run(tmp_path, 'r')
