"""Join diagnostic admission events to exact tokenized dev prompts, without gold."""
import argparse
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path
from transformers import AutoTokenizer
from cacheflow.v2_replay import load_trace
from v3_model import get_model


def read(path):return [json.loads(l) for l in Path(path).read_text().splitlines()]


def union_length(intervals):
    end=0;total=0
    for start,stop in sorted(intervals):
        total+=max(0,stop-max(start,end));end=max(end,stop)
    return total


def main():
    p=argparse.ArgumentParser();p.add_argument('run_ids',nargs='+');p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    tok=AutoTokenizer.from_pretrained(get_model('qwen3-4b')['path'],local_files_only=True)
    trace=load_trace(a.trace);by_sha={};groups=defaultdict(list)
    for row in trace:
        ids=tok.encode(row.prompt,add_special_tokens=False);assert len(ids)==row.input_tokens
        sha=hashlib.sha256(','.join(map(str,ids)).encode()).hexdigest()
        assert sha not in by_sha,'diagnostic requires unique exact prompt token sequences'
        by_sha[sha]=row;groups[row.sample_id].append(ids)
    common={}
    for group,sequences in groups.items():
        lo=min(sequences);hi=max(sequences);n=0
        for x,y in zip(lo,hi):
            if x!=y:break
            n+=1
        common[group]=n
    events=read('results/v3/raw/sglang_admission_events.jsonl');runs=[]
    for rid in a.run_ids:
        raw=Path('results/v3/raw/sglang');base=Path('results/v3/sglang')
        assert not (base/f'{rid}.invalid').exists()
        setup=json.loads((base/f'{rid}.setup.json').read_text());assert setup['runtime']['profile_transfers']
        requests=read(raw/f'{rid}.jsonl');assert all(r['status']=='ok' for r in requests)
        start=min(r['scheduled_arrival_ns'] for r in requests);stop=max(r['complete_ns'] for r in requests)
        window=[e for e in events if start<=e['monotonic_ns']<=stop]
        mapping={e['rid']:by_sha[e['input_ids_sha256']] for e in window
            if e['kind']=='request' and e['input_ids_sha256'] in by_sha}
        assert len(mapping)==len(trace)==len(requests)
        selected=[e for e in window if e['kind'] in {'add_one_req','add_chunked_req'} and e['selected'] and e['rid'] in mapping]
        assert {e['rid'] for e in selected}==mapping.keys()
        intervals=defaultdict(list);context_compute=Counter();total=0
        batches=[];segments=[]
        for e in selected:
            row=mapping[e['rid']];begin=e['after_gpu_prefix_tokens'];end=begin+e['after_extend_tokens']
            assert 0<=begin<end<=row.input_tokens,(rid,e)
            count=e.get('before',{}).get('already_selected',0)
            if e['kind']=='add_chunked_req' or count==0:batches.append([])
            assert batches and count==len(batches[-1]),(rid,e,count)
            segment=dict(request_id=row.request_id,sample_id=row.sample_id,begin=begin,end=end,
                relative_ms=(e['monotonic_ns']-start)/1e6,batch=len(batches)-1,
                host_hit_before=e.get('before',{}).get('host_hit_tokens'))
            batches[-1].append(segment);segments.append(segment)
            total+=end-begin
            limit=common[row.sample_id];end=min(end,limit)
            if begin<end:
                context_compute[row.sample_id]+=end-begin;intervals[row.sample_id].append((begin,end))
        metrics=json.loads((base/f'{rid}.metrics_summary.json').read_text())['counter_deltas']
        reported=metrics['sglang:uncached_prompt_tokens_histogram_sum']
        per_group=[dict(sample_id=g,common_prefix_tokens=common[g],scheduled_context_prefill_tokens=context_compute[g],
            covered_context_positions=union_length(intervals[g]),
            repeated_context_prefill_tokens=context_compute[g]-union_length(intervals[g])) for g in sorted(common)]
        loads=[e for e in window if e['kind']=='load_back']
        in_batch_repeated=0
        for batch in batches:
            for g in common:
                spans=[(s['begin'],min(s['end'],common[g])) for s in batch
                       if s['sample_id']==g and s['begin']<min(s['end'],common[g])]
                in_batch_repeated+=sum(end-begin for begin,end in spans)-union_length(spans)
        runs.append(dict(run_id=rid,requests=len(mapping),selected_prefill_chunks=len(selected),
            scheduled_prefill_tokens=total,native_uncached_prompt_tokens=reported,
            scheduled_matches_native_uncached=(total==reported),
            selected_initial_host_hit_tokens=sum(e['before']['host_hit_tokens'] for e in selected if e['kind']=='add_one_req'),
            native_load_calls=len(loads),native_load_tokens=sum(e['loaded_tokens'] for e in loads),
            load_outcomes=loads,by_conversation=per_group,
            reconstructed_prefill_batches=len(batches),same_batch_repeated_context_tokens=in_batch_repeated,
            selected_segments=segments))
    a.output.write_text(json.dumps(dict(scope='Instrumented diagnostic; exact token-interval scheduling evidence, not a kernel-duration or overlap measurement',runs=runs),indent=2)+'\n')
    for r in runs:print(r['run_id'],r['scheduled_prefill_tokens'],r['native_uncached_prompt_tokens'],r['native_load_calls'],r['by_conversation'])


if __name__=='__main__':main()
