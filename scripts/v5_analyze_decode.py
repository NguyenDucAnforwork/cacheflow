"""Completion latency and client decode proxy from existing captured timestamps.

No individual token timestamps were saved: these are not exact ITL quantiles.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def summarize(rows,duration_s):
    assert rows and all(r['status']=='ok' for r in rows)
    assert duration_s>0 and all(r['output_tokens']>=1 for r in rows)
    assert all(r['scheduled_arrival_ns']<=r['first_token_ns']<=r['complete_ns'] for r in rows)
    completion=[(r['complete_ns']-r['scheduled_arrival_ns'])/1e6 for r in rows]
    after_first=[(r['complete_ns']-r['first_token_ns'])/1e6 for r in rows]
    eligible=[r for r in rows if r['output_tokens']>=2]
    proxies=[(r['complete_ns']-r['first_token_ns'])/1e6/(r['output_tokens']-1) for r in eligible]
    def quantiles(values):return {f'p{p}':float(np.percentile(values,p)) for p in [50,95,99]} if values else None
    return dict(requests=len(rows),completion_latency_ms=quantiles(completion),after_first_to_close_ms=quantiles(after_first),
        client_tpot_proxy_ms=quantiles(proxies),proxy_eligible_requests=len(eligible),single_token_responses=len(rows)-len(eligible),
        generated_tokens=sum(r['output_tokens'] for r in rows),
        workload_output_tokens_per_s=sum(r['output_tokens'] for r in rows)/duration_s,
        warning='Proxy includes stream chunking, special-token accounting and final stream/metadata close overhead; one-token outputs are excluded, not zero-filled. Output tokens/s uses full workload duration and can be arrival-limited.')


def analyze(run_id):
    sg=Path(f'results/v3/sglang/{run_id}.setup.json').exists();root=Path('results/v3/raw/sglang' if sg else 'results/v3/raw')
    data=(root/f'{run_id}.jsonl').read_bytes();rows=[json.loads(l) for l in data.splitlines()]
    s=json.loads((root/f'{run_id}.summary.json').read_text());assert len(rows)==s['requests']==s['successes'] and not s['errors']
    assert len({r['request_id'] for r in rows})==len(rows)
    result=dict(run_id=run_id,prompt_version=s['prompt_version'],trace_sha256=s['trace_sha256'],
        request_file_sha256=hashlib.sha256(data).hexdigest(),**summarize(rows,s['duration_s']))
    if sg:
        samples=[json.loads(l) for l in (root/f'{run_id}.metrics.jsonl').read_text().splitlines()]
        first,last=samples[0]['sglang'],samples[-1]['sglang'];cs='sglang:inter_token_latency_seconds_count';ss='sglang:inter_token_latency_seconds_sum'
        dc=last[cs]-first[cs] if cs in first and cs in last else None
        ds=last[ss]-first[ss] if ss in first and ss in last else None
        result['native_itl_observation_count']=dc
        result['native_itl_mean_ms']=ds/dc*1000 if dc is not None and ds is not None and dc>0 and ds>=0 else None
        result['native_itl_sample_endpoints_ns']=[samples[0]['timestamp_ns'],samples[-1]['timestamp_ns']]
        result['native_itl_scope']='Native sampled-window histogram sum/count difference only; no query-start timestamps, retained buckets or per-token/request join. This is an observed-window mean, not exact full-run ITL coverage or ITL p95.'
    else:
        result['native_itl_mean_ms']=None;result['native_itl_scope']='The frozen main sampler did not retain native ITL counters; no retrospective value invented.'
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('run_id',nargs='?');p.add_argument('--validation',action='store_true');p.add_argument('--stage',choices=['validation','confirmation','full']);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not (a.validation and a.stage), 'choose one stage flag'
    stage='validation' if a.validation else a.stage
    assert bool(a.run_id)!=bool(stage), 'choose a single run ID or an audited stage'
    if stage:
        path=Path(f'results/v3/v5r2_{stage}_audit.json');audit=json.loads(path.read_text())
        n,requests={'validation':(57,2820),'confirmation':(27,1080),'full':(17,33762)}[stage]
        assert len(audit['runs'])==n and audit['requests']==requests and not audit['errors']
        rows=[analyze(r['run_id']) for r in audit['runs']];by={r['run_id']:r for r in rows};pairs=[]
        for pair in audit['pairs']:
            left,right=by[pair['a']],by[pair['b']]
            pairs.append(dict(a=pair['a'],b=pair['b'],
                completion_p95_delta_pct=100*(right['completion_latency_ms']['p95']/left['completion_latency_ms']['p95']-1),
                generated_tokens_a=left['generated_tokens'],generated_tokens_b=right['generated_tokens']))
        result=dict(source_audit_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            stage=stage,scope='Complete audited V5 revision2 stage. Client TPOT proxies are request-level averages, not individual-token ITL. Generated-token volume varies with batching/answers. No throughput-capacity or quality-equivalence inference.',runs=rows,pairs=pairs)
    else:result=analyze(a.run_id)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print('Analyzed',len(result['runs']) if stage else 1,'runs:',a.output)


if __name__=='__main__':main()
