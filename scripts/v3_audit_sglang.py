"""Validate native HiCache runs without relabelling its counters as vLLM counters."""
import hashlib
import json
from pathlib import Path


def lines(path):return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def audit(rid):
    base=Path('results/v3/sglang');raw=Path('results/v3/raw/sglang')
    assert not (base/f'{rid}.invalid').exists()
    s=json.loads((raw/f'{rid}.summary.json').read_text())
    setup=json.loads((base/f'{rid}.setup.json').read_text())
    m=json.loads((base/f'{rid}.metrics_summary.json').read_text())
    rows=lines(raw/f'{rid}.jsonl');out=lines(raw/f'{rid}.outputs.jsonl')
    by={x['request_id']:x for x in rows};captured={x['request_id']:x for x in out}
    assert len(by)==len(rows)==len(captured)==len(out)==s['requests']==s['successes']
    assert by.keys()==captured.keys() and s['errors']==0
    assert s['engine_kind']=='sglang' and s['engine_version']==setup['server_config']['version']
    for rid,row in by.items():
        assert row['status']=='ok' and row['input_tokens']==row['server_prompt_tokens']
        assert row['output_tokens']<=s['output_tokens_budget']
        assert hashlib.sha256(captured[rid]['output'].encode()).hexdigest()==row['output_hash']
    c=m['counter_deltas']
    total=sum(row['input_tokens'] for row in rows)
    assert c['sglang:prompt_tokens_total']==total
    cached=c['sglang:cached_tokens_total'];uncached=c['sglang:uncached_prompt_tokens_histogram_sum']
    assert cached+uncached==total
    return dict(run_id=s['run_id'],requests=len(rows),errors=s['errors'],
        p50_ms=s['arrival_ttft_p50_ms'],p95_ms=s['arrival_ttft_p95_ms'],p99_ms=s['arrival_ttft_p99_ms'],
        total_prompt_tokens=total,native_cached_tokens=cached,native_uncached_tokens=uncached,
        native_host_promoted_tokens=c.get('sglang:load_back_tokens_total'),
        native_load_back_cpu_duration_s=c.get('sglang:load_back_duration_seconds_sum'),
        same_pinned_prompt_token_counts=True,output_hashes_verified=True)


if __name__=='__main__':
    runs=['v3-sglang-lpm16-dev3-qps2-s101-r2','v3-sglang-lpm16-dev3-qps2-s102','v3-sglang-lpm16-dev3-qps2-s103']
    result=[audit(r) for r in runs]
    Path('results/v3/sglang/native_three_seeds_audit.json').write_text(json.dumps(dict(
        checks=result,counter_scope='Native SGLang source semantics; host-promotion counts/CPU enqueue timers are not full DMA timing.'),indent=2)+'\n')
    print('Native HiCache audit passed:',len(result),'runs;',sum(x['requests'] for x in result),'requests')
