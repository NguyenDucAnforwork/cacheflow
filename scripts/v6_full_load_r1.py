"""Strict source accounting and paired V3 admission comparisons."""
from v6_full_analysis_r1 import validate_retained_audit_interruption
import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path


def read_jsonl(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def load(run_id):
    base=Path('results/v3');raw=base/'raw'
    diagnostic=base/'residency_namespace_diagnostic.json'
    if diagnostic.exists() and run_id in json.loads(diagnostic.read_text())['runs']:
        raise ValueError('diagnostic: incompatible external hash namespace')
    validate_retained_audit_interruption(run_id)
    s=json.loads((raw/f'{run_id}.summary.json').read_text())
    m=json.loads((base/f'{run_id}.metrics_summary.json').read_text())
    r=read_jsonl(raw/f'{run_id}.jsonl');g=read_jsonl(raw/f'{run_id}.gateway.jsonl')
    by={x['request_id']:x for x in r};gate={x['request_id']:x for x in g}
    if len(by)!=len(r) or by.keys()!=gate.keys():raise ValueError('request IDs not unique/matched')
    if s['errors'] or s['successes']!=len(r):raise ValueError('failed run')
    if any(x['status']!='ok' or x['server_prompt_tokens']!=x['input_tokens'] for x in r):raise ValueError('request/token error')
    if any(x['output_tokens']>s['output_tokens_budget'] for x in r):raise ValueError('output budget')
    if any(x['run_id']!=run_id for x in [*r,*g]):raise ValueError('provenance error')
    outputs=read_jsonl(raw/f'{run_id}.outputs.jsonl')
    captured={x['request_id']:x for x in outputs}
    if len(captured)!=len(outputs) or captured.keys()!=by.keys():raise ValueError('captured output IDs')
    if any(hashlib.sha256(captured[rid]['output'].encode()).hexdigest()!=x['output_hash'] for rid,x in by.items()):raise ValueError('captured text hash')
    if any(x['status']!='ok' or x['input_tokens']!=by[rid]['input_tokens'] for rid,x in gate.items()):raise ValueError('gateway mismatch')
    c=m['counter_deltas']['vllm']
    if c['vllm:prompt_tokens_total']!=sum(x['input_tokens'] for x in r):raise ValueError('missing metrics')
    if c['vllm:prompt_tokens_cached_total']+c['vllm:request_prefill_kv_computed_tokens_sum']!=c['vllm:prompt_tokens_total']:raise ValueError('incomplete source accounting')
    return dict(summary=s,metrics=m,requests=by,gateway=gate)


def compare(a,b):
    for key in ['trace_sha256','model_revision','gpu_kv_bytes','max_model_len','output_tokens_budget',
                'source_sha256','prompt_version','vllm_version','lmcache_version','engine_pid','lmcache_pid']:
        if a['summary'].get(key)!=b['summary'].get(key):raise ValueError('unmatched '+key)
    if a['requests'].keys()!=b['requests'].keys():raise ValueError('IDs differ')
    pairs=[]
    for rid,x in a['requests'].items():
        y=b['requests'][rid]
        if x['prompt_sha256']!=y['prompt_sha256']:raise ValueError('prompt changed')
        pairs.append(dict(request_id=rid,sample_id=x['sample_id'],a_ms=x['arrival_ttft_ms'],b_ms=y['arrival_ttft_ms'],
                          delta_ms=y['arrival_ttft_ms']-x['arrival_ttft_ms'],hash_equal=x['output_hash']==y['output_hash']))
    return dict(a=a['summary']['run_id'],b=b['summary']['run_id'],trace_sha256=a['summary']['trace_sha256'],
        p50_delta_pct=100*(b['summary']['arrival_ttft_p50_ms']/a['summary']['arrival_ttft_p50_ms']-1),
        p95_delta_pct=100*(b['summary']['arrival_ttft_p95_ms']/a['summary']['arrival_ttft_p95_ms']-1),
        a_metrics=a['metrics'],b_metrics=b['metrics'],paired_requests=pairs)


def main():
    p=argparse.ArgumentParser();p.add_argument('--a');p.add_argument('--b');p.add_argument('--output',type=Path)
    args=p.parse_args()
    if args.a:
        result=compare(load(args.a),load(args.b));args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['a_metrics','b_metrics','paired_requests']},indent=2));return
    rows=[]
    for file in sorted(Path('results/v3/raw').glob('*.summary.json')):
        s=json.loads(file.read_text())
        try:run=load(s['run_id'])
        except (ValueError,FileNotFoundError) as e:print('SKIP',s['run_id'],str(e));continue
        c=run['metrics']['counter_deltas']['vllm']
        setup=json.loads(Path(f'results/v3/{s["run_id"]}.setup.json').read_text())
        rows.append(dict(run_id=s['run_id'],policy=s['policy'],cap=setup['runtime']['max_inflight'],
            profiled=setup['runtime']['profile'] or setup['runtime'].get('kv_events',False),
            batch_invariant=setup['runtime'].get('batch_invariant',False),
            p50_ms=s['arrival_ttft_p50_ms'],p95_ms=s['arrival_ttft_p95_ms'],
            p99_ms=s['arrival_ttft_p99_ms'],requests_per_s=s['requests_per_s'],requests=s['requests'],
            new_prefill=c['vllm:request_prefill_kv_computed_tokens_sum'],
            cpu_tokens=c['vllm:prompt_tokens_source_external_kv_transfer_total'],
            gpu_tokens=c['vllm:prompt_tokens_source_local_cache_hit_total'],
            preemptions=c['vllm:num_preemptions_total']))
    with Path('results/v3/run_table.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    for r in rows:print(r['run_id'],round(r['p95_ms']),r['cpu_tokens'])


if __name__=='__main__':main()
