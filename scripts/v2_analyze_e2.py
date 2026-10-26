"""Audit B1/B2 LoCoMo tiering runs and emit compact, prompt-free evidence."""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import statistics
from pathlib import Path


COUNTERS = {
    'computed_prefill_tokens': ('vllm', 'vllm:request_prefill_kv_computed_tokens_sum'),
    'gpu_prefix_hit_tokens': ('vllm', 'vllm:prefix_cache_hits_total'),
    'external_prefix_hit_tokens': ('vllm', 'vllm:external_prefix_cache_hits_total'),
    'cached_prompt_tokens': ('vllm', 'vllm:prompt_tokens_cached_total'),
    'l1_read_chunks': ('lmcache', 'lmcache_mp_l1_read_chunks_total'),
    'l1_write_chunks': ('lmcache', 'lmcache_mp_l1_write_chunks_total'),
    'loaded_chunks': ('lmcache', 'lmcache_mp_num_chunks_loaded_total'),
}


def jsonl(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def indexed(rows):
    result = {r['request_id']: r for r in rows}
    if not rows or len(result) != len(rows):
        raise ValueError('empty or duplicate request IDs')
    return result


def load_run(root, run_id):
    base = root / 'results/v2'
    raw = base / 'raw'
    if (base / f'{run_id}.invalid').exists():
        raise ValueError(f'invalid run: {run_id}')
    summary = json.loads((raw / f'{run_id}.summary.json').read_text())
    metrics = json.loads((base / f'{run_id}.metrics_summary.json').read_text())
    requests = indexed(jsonl(raw / f'{run_id}.jsonl'))
    gateway = indexed(jsonl(raw / f'{run_id}.gateway.jsonl'))
    outputs = indexed(jsonl(raw / f'{run_id}.outputs.jsonl'))
    if summary['run_id'] != run_id or summary['requests'] != len(requests):
        raise ValueError('run summary mismatch')
    if summary['errors'] or summary['successes'] != len(requests):
        raise ValueError('failed run')
    if requests.keys() != gateway.keys() or requests.keys() != outputs.keys():
        raise ValueError('request/gateway/output IDs differ')
    for request_id, r in requests.items():
        if r['status'] != 'ok' or gateway[request_id]['status'] != 'ok':
            raise ValueError('failed request')
        if r['run_id'] != run_id or r['trace_sha256'] != summary['trace_sha256']:
            raise ValueError('request provenance mismatch')
        if r['server_prompt_tokens'] != r['input_tokens'] or gateway[request_id]['input_tokens'] != r['input_tokens']:
            raise ValueError('prompt token count mismatch')
        if r['output_tokens'] is None or r['output_tokens'] > summary['output_tokens_budget']:
            raise ValueError('output budget violation')
        import hashlib
        if hashlib.sha256(outputs[request_id]['output'].encode()).hexdigest() != r['output_hash']:
            raise ValueError('captured output hash mismatch')
    return {'summary': summary, 'metrics': metrics, 'requests': requests, 'gateway': gateway}


def compare(b1, b2):
    x, y = b1['summary'], b2['summary']
    if (x['mode'], x['policy'], y['mode'], y['policy']) != ('B1', 'fifo', 'B2', 'fifo'):
        raise ValueError('requires B1 FIFO and B2 FIFO')
    for k in ('trace_sha256', 'gpu_kv_bytes', 'model_revision', 'model_name', 'max_model_len',
              'output_tokens_budget', 'source_sha256', 'prompt_version', 'protocol', 'arrival',
              'python_version', 'vllm_version', 'lmcache_version', 'transformers_version'):
        if x.get(k) is None or x[k] != y.get(k):
            raise ValueError(f'unmatched metadata: {k}')
    if b1['requests'].keys() != b2['requests'].keys():
        raise ValueError('request ID mismatch')
    paired = []
    for rid in sorted(b1['requests']):
        a, b = b1['requests'][rid], b2['requests'][rid]
        for k in ('prompt_sha256', 'input_tokens', 'server_prompt_tokens', 'sample_id', 'qa_index'):
            if a[k] != b[k]:
                raise ValueError(f'unmatched request {rid}: {k}')
        paired.append({'request_id': rid, 'sample_id': a['sample_id'],
                       'b1_ttft_ms': a['arrival_ttft_ms'], 'b2_ttft_ms': b['arrival_ttft_ms'],
                       'delta_b2_minus_b1_ms': b['arrival_ttft_ms'] - a['arrival_ttft_ms'],
                       'output_hash_equal': a['output_hash'] == b['output_hash'],
                       'b1_output_tokens': a['output_tokens'], 'b2_output_tokens': b['output_tokens']})
    counters = {}
    for label, (src, name) in COUNTERS.items():
        a = b1['metrics']['counter_deltas'][src].get(name)
        b = b2['metrics']['counter_deltas'][src].get(name)
        counters[label] = {'b1': a, 'b2': b, 'delta': b - a if a is not None and b is not None else None}
    latencies = {}
    for name in ('arrival_ttft_p50_ms', 'arrival_ttft_p95_ms', 'arrival_ttft_p99_ms', 'requests_per_s'):
        a, b = x[name], y[name]
        latencies[name] = {'b1': a, 'b2': b, 'delta': b - a,
                           'relative_change_pct': 100 * (b / a - 1)}
    return {'b1_run_id': x['run_id'], 'b2_run_id': y['run_id'], 'trace_sha256': x['trace_sha256'],
            'gpu_kv_bytes': x['gpu_kv_bytes'], 'requests': len(paired), 'errors': 0,
            'output_hash_matches': sum(r['output_hash_equal'] for r in paired),
            'latency': latencies, 'counters': counters, 'paired_requests': paired,
            'note': 'Cold-start different-engine comparison; output agreement is not a QA score.'}


def run_level_interval(values):
    """Exploratory paired Student-t interval; runs, never requests, are units."""
    n = len(values)
    mean = statistics.mean(values)
    # Explicit critical values avoid an optional scipy dependency.
    critical = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571}.get(n)
    half = critical * statistics.stdev(values) / n**0.5 if critical else None
    return {'n_runs': n, 'mean': mean, 'min': min(values), 'max': max(values),
            'exploratory_t95_interval': [mean - half, mean + half] if half is not None else None}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('.'))
    p.add_argument('--seeds', type=int, nargs='+', default=[17, 29, 43])
    p.add_argument('--budgets', type=int, nargs='+', default=[4, 8])
    args = p.parse_args()
    base = args.root / 'results/v2'
    comparisons, table = [], []
    for gib, seed in itertools.product(args.budgets, args.seeds):
        ids = [f'v2-e2-{arm}-{gib}g-dev3-qps02-s{seed}' for arm in ('b1', 'b2')]
        arms = [load_run(args.root, rid) for rid in ids]
        c = compare(*arms)
        c['seed'] = seed
        comparisons.append(c)
        (base / f'e2-{gib}g-s{seed}.compare.json').write_text(json.dumps(c, indent=2) + '\n')
        for run in arms:
            s, m = run['summary'], run['metrics']
            row = {k: s[k] for k in ('run_id', 'mode', 'requests', 'errors', 'arrival_ttft_p50_ms',
                                     'arrival_ttft_p95_ms', 'arrival_ttft_p99_ms', 'requests_per_s', 'duration_s')}
            row.update(gpu_kv_gib=gib, seed=seed, vram_peak_mib=m['vram_peak_mib'])
            for label, (src, name) in COUNTERS.items():
                row[label] = m['counter_deltas'][src].get(name)
            sampled = jsonl(Path(s['metrics_path']))
            for metric, field in [('vllm:num_requests_waiting', 'engine_waiting_peak'),
                                  ('vllm:kv_cache_usage_perc', 'kv_usage_peak')]:
                row[field] = max((r.get('vllm', {}).get(metric, 0) for r in sampled), default=None)
            row['admission_wait_p95_ms'] = sorted(g['admission_wait_ms'] for g in run['gateway'].values())[int(.95*(len(run['gateway'])-1))]
            table.append(row)
    with (base / 'e2_runs.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    summary = {}
    for gib in args.budgets:
        group = [c for c in comparisons if c['gpu_kv_bytes'] == gib * 1024**3]
        summary[str(gib)] = {'p95_delta_ms': run_level_interval([c['latency']['arrival_ttft_p95_ms']['delta'] for c in group]),
                             'p95_relative_change_pct': run_level_interval([c['latency']['arrival_ttft_p95_ms']['relative_change_pct'] for c in group]),
                             'p50_relative_change_pct': run_level_interval([c['latency']['arrival_ttft_p50_ms']['relative_change_pct'] for c in group]),
                             'output_hash_matches': sum(c['output_hash_matches'] for c in group),
                             'output_pairs': sum(c['requests'] for c in group)}
    (base / 'e2_aggregate.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
