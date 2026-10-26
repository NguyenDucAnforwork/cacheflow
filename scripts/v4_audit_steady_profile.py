"""Cross-check GPU timeline coverage against independent host-promotion/event ledgers."""
import collections
import gzip
import hashlib
import json
import statistics
from pathlib import Path


def main():
    setup_path=Path('results/v3/sglang/v4_steady_profile_setup.json')
    setup=json.loads(setup_path.read_text())
    events=[json.loads(line) for line in Path('results/v3/raw/sglang_transfer_events.jsonl').read_text().splitlines()]
    phases=[]
    for p in setup['phases']:
        rows=[e for e in events if e.get('phase')=='H2D' and p['start_ns']<=e['launch_monotonic_ns']<p['end_ns']]
        assert len(rows)==12 and sum(e['tokens'] for e in rows)==p['host_promoted_tokens']
        assert all(e['io_backend']=='direct' and e['layers']==36 for e in rows)
        expected=int(p['host_promoted_tokens'])*147456
        assert sum(e['bytes'] for e in rows)==expected
        phases.append(dict(phase=p['phase'],requests=12,host_promoted_tokens=p['host_promoted_tokens'],
            expected_payload_bytes=expected,cuda_event_payload_bytes=sum(e['bytes'] for e in rows),
            summed_load_stream_span_ms=sum(e['elapsed_gpu_ms'] for e in rows),
            median_effective_GB_s=statistics.median(e['bandwidth_GB_s'] for e in rows),
            ttft_p50_ms=p['ttft_p50_ms'],ttft_p95_ms=p['ttft_p95_ms']))
    path=Path(setup['cuda_traces'][0]);trace=json.loads(gzip.decompress(path.read_bytes()))['traceEvents']
    copies=[e for e in trace if e.get('cat')=='gpu_memcpy' and 'HtoD' in e.get('name','')]
    visible=sum(e['args']['bytes'] for e in copies)
    expected=next(p['expected_payload_bytes'] for p in phases if p['phase']=='gpu_profile')
    # Visible copies also include input/index tensors; this ratio is an upper
    # bound on represented KV payload, not a claim each observed byte is KV.
    ratio=visible/expected
    assert ratio<0.01,'Reinspect classification if profiler coverage changes'
    result=dict(scope='Direct CPU-hot diagnostic; closed-loop12 requests/phase,4 generated tokens; not main performance',
        setup_sha256=hashlib.sha256(setup_path.read_bytes()).hexdigest(),
        trace_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),phases=phases,
        profiler_p95_delta_vs_off_mean_pct=setup['profiler_p95_delta_vs_off_mean_pct'],
        trace_categories=dict(collections.Counter(e.get('cat','') for e in trace)),
        visible_h2d_copy_events=len(copies),visible_h2d_copy_bytes=visible,
        visible_h2d_sum_duration_ms=sum(e['dur'] for e in copies)/1000,
        visible_h2d_bytes_fraction_of_expected_kv=ratio,
        invalid_cuda_runtime_events=sum(e.get('cat')=='cuda_runtime' and e.get('name')=='INVALID' for e in trace),
        dma_model_overlap=None,
        overlap_unavailable_reason='Ordinary gpu_memcpy coverage accounts for <1% of independently verified KV payload. CPU launch and CUDA elapsed duration cannot locate the copy on the GPU absolute timeline.',
        interpretation='CUDA events measure load-stream span, including enqueue gaps/dependencies between events; not pure PCIe busy time. Small off/on/off difference is diagnostic-specific. Batched Direct copy API is a possible coverage cause, not proven by INVALID labels alone.')
    out=Path('results/v3/sglang/v4_steady_profile_audit.json');out.write_text(json.dumps(result,indent=2)+'\n')
    print('Verified',len(phases),'phases; visible H2D bytes',visible,'of expected KV',expected,'ratio',ratio)


if __name__=='__main__':main()
