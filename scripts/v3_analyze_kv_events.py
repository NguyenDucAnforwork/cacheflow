"""Audit real LMCache MP transfer bytes separately from engine-consumed KV tokens."""
import argparse
import collections
import json
import statistics
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--run-ids',nargs='+',required=True)
    p.add_argument('--events',type=Path,default=Path('results/v3/raw/kv_events.jsonl'))
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    all_events=[json.loads(l) for l in a.events.read_text().splitlines()];results=[]
    for rid in a.run_ids:
        events=[e for e in all_events if rid+'-' in str(e.get('session_id',''))]
        pending={};phases=collections.defaultdict(list)
        for e in events:
            name=e['event_type'];phase=name.rsplit('.',1)[0]
            key=(e['session_id'],phase,e['metadata'].get('device'))
            if name.endswith('.start'):
                assert key not in pending,('duplicate start',key)
                pending[key]=e
            elif name.endswith('.end'):
                assert key in pending,('unmatched end',key)
                start=pending.pop(key);dt=e['timestamp']-start['timestamp'];assert dt>=0
                phases[phase].append(dict(duration_s=dt,metadata=e['metadata']))
        assert not pending,('unfinished phase events',len(pending))
        summaries={}
        for name,values in phases.items():
            durations=[v['duration_s'] for v in values]
            rates=[v['metadata'].get('total_bytes',0)/v['duration_s']/1e9 for v in values
                   if v['duration_s']>0 and v['metadata'].get('total_bytes',0)>0]
            summaries[name]=dict(events=len(values),sum_duration_s=sum(durations),
                median_duration_ms=statistics.median(durations)*1000,
                total_bytes=sum(v['metadata'].get('total_bytes',0) for v in values),
                median_GB_s=statistics.median(rates) if rates else None)
        metrics=json.loads(Path(f'results/v3/{rid}.metrics_summary.json').read_text())['counter_deltas']['vllm']
        results.append(dict(run_id=rid,phases=summaries,
            engine_consumed_cpu_tokens=metrics['vllm:prompt_tokens_source_external_kv_transfer_total']))
    a.output.write_text(json.dumps(dict(runs=results,
        scope='Batch-invariant/lightweight-instrumented diagnostic; event bytes and durations retain LMCache semantics; no overlap claim'),indent=2)+'\n')
    for r in results:print(r['run_id'],r['phases'])


if __name__=='__main__':main()
