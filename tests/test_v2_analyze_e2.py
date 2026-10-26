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
