"""Correlate CUDA model kernels, KV transfer events and gateway phases."""
import argparse
import collections
import gzip
import json
import statistics
from pathlib import Path


def union(intervals):
    merged=[]
    for a,b in sorted(intervals):
        if b<=a: continue
        if merged and a<=merged[-1][1]: merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else: merged.append((a,b))
    return merged


def duration(intervals):
    return sum(b-a for a,b in union(intervals))


def intersection(a,b):
    a,b=union(a),union(b);out=[];i=j=0
    while i<len(a) and j<len(b):
        lo,hi=max(a[i][0],b[j][0]),min(a[i][1],b[j][1])
        if hi>lo:out.append((lo,hi))
        if a[i][1]<b[j][1]:i+=1
        else:j+=1
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--events',type=Path,required=True);p.add_argument('--gateway',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    trace=json.loads(gzip.open(args.trace,'rt').read())
    base=trace['baseTimeNanoseconds']/1e9
    kernels=[e for e in trace['traceEvents'] if e.get('cat')=='kernel' and e.get('ph')=='X']
    intervals=[(base+e['ts']/1e6,base+(e['ts']+e['dur'])/1e6) for e in kernels]
    window=(min(a for a,b in intervals),max(b for a,b in intervals))
    by_name=collections.Counter()
    for e in kernels:by_name[e['name']]+=e['dur']/1e6
    pending={};phases=collections.defaultdict(list)
    for e in map(json.loads,args.events.read_text().splitlines()):
        name=e['event_type'];phase=name.rsplit('.',1)[0]
        key=(e['session_id'],phase,e['metadata'].get('device'))
        if name.endswith('.start'):pending[key]=e
        elif name.endswith('.end') and key in pending:
            start=pending.pop(key);dt=e['timestamp']-start['timestamp']
            phases[phase].append(dict(start=start['timestamp'],end=e['timestamp'],duration_s=dt,
                session_id=e['session_id'],metadata=e['metadata']))
    summary={}
    for phase,events in phases.items():
        lat=[e['duration_s'] for e in events]
        rates=[e['metadata']['total_bytes']/e['duration_s']/1e9 for e in events
               if e['metadata'].get('total_bytes',0)>0 and e['duration_s']>0]
        ints=[(e['start'],e['end']) for e in events]
        clipped=intersection(ints,[window])
        summary[phase]=dict(events=len(events),sum_duration_s=sum(lat),median_duration_s=statistics.median(lat),
            max_duration_s=max(lat),median_GB_s=statistics.median(rates) if rates else None,
            total_bytes=sum(e['metadata'].get('total_bytes',0) for e in events),
            union_s_in_kernel_window=duration(clipped),overlap_with_model_kernels_s=duration(intersection(clipped,intervals)))
    gateway=list(map(json.loads,args.gateway.read_text().splitlines()))
    ingress={}
    for field in ['ingress_prepare_ms','tokenize_ms','prefix_hash_ms','admission_wait_ms']:
        values=[r[field] for r in gateway if r.get(field)is not None]
        ingress[field]=dict(n=len(values),median=statistics.median(values),max=max(values)) if values else None
    result=dict(profile_trace=str(args.trace),event_trace=str(args.events),kernel_window_wall_s=window,
        kernel_window_duration_s=window[1]-window[0],model_kernel_union_s=duration(intervals),
        top_kernels_s=by_name.most_common(15),kv_phases=summary,ingress=ingress,
        warning='Instrumented diagnostic only. PyTorch profiling adds substantial overhead; use unprofiled runs for performance claims. Transfer events cover full run; overlap is clipped to CUDA trace window.')
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__': main()
