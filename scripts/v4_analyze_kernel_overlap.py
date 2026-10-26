"""GPU-assisted HiCache kernel/model timeline overlap, separate from Direct DMA.

Only runs after the dedicated kernel diagnostic exists. All intersections use
one GPU trace clock. An I/O kernel interval is not a PCIe bus utilization trace.
"""
import collections
import gzip
import hashlib
import json
from pathlib import Path
from v3_analyze_profile import duration,intersection,union


def main():
    setup_path=Path('results/v3/sglang/v4_kernel_gpu_steady.setup.json')
    setup=json.loads(setup_path.read_text())
    assert setup['runtime']['io_backend']=='kernel' and setup['runtime']['profile_transfers']
    assert setup['server_config']['hicache_mem_layout']=='page_first'
    phases=setup['phases'];on=next(p for p in phases if p['profiled'])
    assert all(p['host_promoted_tokens']==on['host_promoted_tokens'] and p['uncached_tokens']==on['uncached_tokens'] for p in phases)
    events=[json.loads(l) for l in Path('results/v3/raw/sglang_transfer_events.jsonl').read_text().splitlines()]
    loads=[e for e in events if e.get('phase')=='H2D' and on['start_ns']<=e['launch_monotonic_ns']<on['end_ns']]
    assert len(loads)==12 and all(e['io_backend']=='kernel' and e['layers']==36 for e in loads)
    assert sum(e['tokens'] for e in loads)==on['host_promoted_tokens']
    trace_path=Path(setup['cuda_traces'][0]);raw=trace_path.read_bytes();trace=json.loads(gzip.decompress(raw))['traceEvents']
    kernels=[e for e in trace if e.get('cat')=='kernel' and e.get('ph')=='X']
    # Native MHA backup uses all_layer, while host promotion uses per_layer.
    # Refuse unknown names/counts rather than treating every kernel as compute.
    transfers=[e for e in kernels if 'hicache_transfer_per_layer' in e['name']]
    assert len(transfers)==12*36,('Inspect actual transfer-kernel names/counts before classification',collections.Counter(e['name'] for e in kernels).most_common(20))
    heavy=[e for e in kernels if any(s in e['name'].lower() for s in
        ['gemm','gemv','batchprefillwithpagedkvcachekernel','batchprefillwithraggedkvcachekernel','batchdecodewithpagedkvcachekernel'])]
    assert heavy and not any(e in transfers for e in heavy)
    def intervals(rows):return [(e['ts']/1e6,(e['ts']+e['dur'])/1e6) for e in rows]
    ti=union(intervals(transfers));ci=union(intervals(heavy));overlap=duration(intersection(ti,ci))
    assert overlap<=min(duration(ti),duration(ci))+1e-9
    result=dict(scope='Kernel/page_first CPU-hot closed-loop12request/4output-token diagnostic; not primary Direct performance. GPU-assisted I/O kernel/model temporal overlap, not pure DMA or bus occupancy.',
        setup_sha256=hashlib.sha256(setup_path.read_bytes()).hexdigest(),trace_sha256=hashlib.sha256(raw).hexdigest(),
        requests=12,host_promoted_tokens=on['host_promoted_tokens'],payload_bytes=sum(e['bytes'] for e in loads),
        transfer_kernel_count=len(transfers),transfer_kernel_names=dict(collections.Counter(e['name'] for e in transfers)),
        heavy_model_kernel_count=len(heavy),heavy_model_kernel_union_s=duration(ci),
        transfer_kernel_union_s=duration(ti),overlap_s=overlap,
        fraction_of_transfer_kernel_time_overlapping_heavy_model=overlap/duration(ti),
        load_stream_span_sum_s=sum(e['elapsed_gpu_ms'] for e in loads)/1000,
        phases=phases,profiler_p95_delta_vs_off_mean_pct=setup['profiler_p95_delta_vs_off_mean_pct'],
        limitations='Intersection proves co-running intervals on the GPU timeline, not useful work hiding, pure PCIe time or causal E2E speedup. Classification intentionally covers GEMM/GEMV/attention rather than all model kernels. Closed-loop cache-hot sequence is not pressure-benchmark concurrency.')
    Path('results/v3/sglang/v4_kernel_gpu_overlap.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Verified GPU-kernel overlap',overlap,'seconds of',duration(ti),'transfer-kernel seconds')


if __name__=='__main__':main()
