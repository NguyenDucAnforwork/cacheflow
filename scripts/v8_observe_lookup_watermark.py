"""Retain actual native pre-allocation watermark inflation, no E2E claim."""
import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
import psutil
from v6_raw_archive import sha
from v7_observe_full_liveness import parsed_lines


def inflated_snapshots(rows):
    found={}
    for r in rows:
        if r['kind']!='connector_metadata':continue
        for rid,t in r['tracker_states'].items():
            if not (t['state']=='PREFETCHING' and t['num_scheduled_tokens']==0 and sum(t['allocated_blocks_per_group'].values())==0):continue
            if t['lmcache_hit_tokens']<=0 or t['num_stored_tokens']<=t['lmcache_hit_tokens']:continue
            ratio=t['num_stored_tokens']/t['lmcache_hit_tokens']
            if rid not in found or ratio>found[rid]['watermark_over_lookup_prefix_ratio']:
                found[rid]=dict(request_id=rid,pid=r['pid'],monotonic_ns=r['monotonic_ns'],tracker=t,watermark_over_lookup_prefix_ratio=ratio)
    return sorted(found.values(),key=lambda r:r['watermark_over_lookup_prefix_ratio'],reverse=True)


def observe(output):
    output=Path(output);assert not output.exists();base=Path('results/v3');reg_path=base/'v8diag3_registration.json';reg=json.loads(reg_path.read_text())
    setup_path=base/'v8diag3-on-target.diagnostic_setup.json';setup=json.loads(setup_path.read_text());assert setup['registration_sha256']==sha(reg_path)
    engine=psutil.Process(setup['engine']['pid']);assert engine.is_running() and engine.status()!=psutil.STATUS_ZOMBIE and engine.create_time()==setup['engine']['birth'] and engine.cmdline()==setup['engine']['argv']
    path='/venv/main/lib/python3.12/site-packages/lmcache/integration/vllm/lmcache_mp_connector.py';assert sha(path)==reg['native_source_sha256'][path]
    rows=[];prefixes=[]
    for p in sorted((base/'raw').glob('v8diag3-probe.*.jsonl')):
        blob=p.read_bytes();rows.extend(parsed_lines(blob));prefixes.append(dict(path=str(p),prefix_bytes=len(blob),prefix_sha256=hashlib.sha256(blob).hexdigest()))
    assert prefixes
    for row in rows:
        if row['kind']=='hook_ready':assert row['source_sha256']==reg['native_source_sha256'][row['source_path']]
    matches=inflated_snapshots(rows)
    phase_counts=dict(Counter('target' if 'v8diag3-on-target-' in r['request_id'] else 'warm' if 'v8diag3-on-warm-' in r['request_id'] else 'unknown' for r in matches))
    result=dict(kind='live_native_lookup_watermark_inflation_observation',synthetic=False,diagnostic_only=True,performance_valid=False,
        observed_monotonic_ns=time.monotonic_ns(),engine_pid=engine.pid,engine_birth=engine.create_time(),
        registration_sha256=sha(reg_path),setup_sha256=sha(setup_path),native_connector_sha256=sha(path),journal_prefixes=prefixes,
        distinct_observed_request_ids=len(matches),distinct_by_phase=phase_counts,max_observed_watermark_over_lookup_prefix_ratio=max([r['watermark_over_lookup_prefix_ratio'] for r in matches] or [0]),
        examples=matches,observer_source_sha256=sha(__file__),
        conditional_cpu_witness_sha256=sha(base/'v8_conditional_lookup_watermark_witness.json'),
        scope='Actual profiled native metadata: PREFETCHING,zero scheduled tokens,zero allocated blocks,stored watermark greater than current cached-prefix length. Max ratio is a watermark/prefix ratio, not a measured lookup-call count. Sampling counts are observed IDs, not complete incidence or uniqueQA. The installed source adds the lookup result to that watermark before allocation; CPU witness establishes conditional later STORE suppression. No actual missed store/DMA bytes, answer quality, latency impact, stall root cause, validated fix or unprofiled behavior is proven here. Original diagnostic continues unchanged.')
    with output.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print('Native pre-allocation inflation:',len(matches),'observed IDs;',phase_counts,'max ratio',result['max_observed_watermark_over_lookup_prefix_ratio'],flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();observe(a.output)
