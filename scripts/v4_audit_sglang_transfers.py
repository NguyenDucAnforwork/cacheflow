"""Validate native CUDA-event coverage against source-labelled HiCache promotions."""
import json
import statistics
from pathlib import Path

events=[json.loads(l) for l in Path('results/v3/raw/sglang_transfer_events.jsonl').read_text().splitlines()]
result=[]
for rid in ['v4-sgprofile-kernel-native-s101','v4-sgprofile-kernel-packing_reuse-s101']:
    samples=[json.loads(l) for l in Path(f'results/v3/raw/sglang/{rid}.metrics.jsonl').read_text().splitlines()]
    selected=[e for e in events if samples[0]['timestamp_ns']<=e['launch_monotonic_ns']<=samples[-1]['timestamp_ns']]
    metrics=json.loads(Path(f'results/v3/sglang/{rid}.metrics_summary.json').read_text())['counter_deltas']
    native=metrics.get('sglang:load_back_tokens_total')
    tokens=sum(e['tokens'] for e in selected)
    if native is not None:assert tokens==native,(rid,tokens,native)
    assert all(e['bytes']==e['tokens']*147456 and e['elapsed_gpu_ms']>0 for e in selected)
    result.append(dict(run_id=rid,observed_loads=len(selected),observed_tokens=tokens,
        observed_bytes=sum(e['bytes'] for e in selected),native_promoted_tokens=native,
        coverage_matches_native_counter=(tokens==native) if native is not None else None,
        sum_load_stream_gpu_ms=sum(e['elapsed_gpu_ms'] for e in selected),
        median_effective_GB_s=statistics.median(e['bandwidth_GB_s'] for e in selected) if selected else None,
        native_cpu_enqueue_sum_s=metrics.get('sglang:load_back_duration_seconds_sum')))
Path('results/v3/sglang/v4_cuda_transfer_audit.json').write_text(json.dumps(dict(
    runs=result,scope='Instrumented diagnostic. GPU load-stream spans exclude index preparation; CPU enqueue timer is separate. No absolute GPU timestamp or overlap estimate. Missing native counters remain null.'),indent=2)+'\n')
for x in result:print(x)
