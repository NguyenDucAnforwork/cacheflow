"""Evaluate the recorded native-HOL metadata prediction without redefining it."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from v6_raw_archive import sha
from v7_observe_full_liveness import parsed_lines


def matching_pairs(rows,start,end):
    selected=sorted([r for r in rows if start<=r['monotonic_ns']<=end],key=lambda r:r['monotonic_ns'])
    failures={};pairs=defaultdict(list)
    for row in selected:
        if row['kind']=='allocation_failure':failures[row['pid']]=row;continue
        if row['kind']!='scheduler' or row['pid'] not in failures:continue
        failed=failures[row['pid']]
        if row['monotonic_ns']-failed['monotonic_ns']>2_500_000_000:continue
        if not (failed['computed_tokens']==0 and failed['held_blocks_per_group']==[0] and failed['arguments']['num_new_tokens']==8192 and failed['free_blocks_after']<512):continue
        if row['free_blocks']!=failed['free_blocks_after']:continue
        by={r['request_id']:r for r in row['requests']};head=by.get(failed['request_id'])
        if head is None or head['status']!='WAITING' or head['num_computed_tokens']!=0:continue
        for holder in row['requests']:
            if holder['request_id']==failed['request_id'] or holder['status']!='WAITING_FOR_REMOTE_KVS':continue
            if holder['request_id'] not in row['finished_recving_kv_req_ids'] or holder['num_computed_tokens']<=0:continue
            if len(holder['block_tables'])!=1:continue
            held=holder['block_tables'][0]['allocated']
            # A metadata bound under the pinned single full-attention Qwen
            # group/no speculation, not a call into a live allocator.
            needed=max((holder['num_tokens']+15)//16-held,0)
            if held>0 and needed<=row['free_blocks']:
                pairs[failed['request_id'],holder['request_id']].append(dict(monotonic_ns=row['monotonic_ns'],free_blocks=row['free_blocks'],holder_held_blocks=held,
                    holder_additional_full_prompt_pages=needed,holder_computed_tokens=holder['num_computed_tokens'],holder_num_tokens=holder['num_tokens'],
                    failed_arguments=failed['arguments']))
    return [dict(failed_head_id=head,finished_holder_id=holder,sampled_pairs=len(points),first=points[0],last=points[-1],
        sampled_span_s=(points[-1]['monotonic_ns']-points[0]['monotonic_ns'])/1e9) for (head,holder),points in pairs.items()]


def evaluate(observation_path,output):
    observation_path=Path(observation_path);output=Path(output);assert not output.exists()
    obs=json.loads(observation_path.read_text());assert obs['diagnostic_only'] and not obs['performance_valid'] and 'native_in_longest_window' in obs
    base=Path('results/v3');reg_path=base/(obs['run_id'].split('-')[0]+'_registration.json');reg=json.loads(reg_path.read_text());assert sha(reg_path)==obs['registration_sha256']
    hp=base/'v8_native_hol_hypothesis_registration.json';hyp=json.loads(hp.read_text());assert reg['amendment_evidence_sha256'][str(hp)]==sha(hp)
    assert hyp['prediction']['failed_new_tokens']==8192 and hyp['prediction']['free_blocks_less_than']==512 and hyp['prediction']['sampled_nonprogress_span_at_least_s']==120
    rows=[]
    for record in obs['native_journal_prefixes']:
        data=Path(record['path']).read_bytes()[:record['prefix_bytes']];assert hashlib.sha256(data).hexdigest()==record['prefix_sha256']
        rows.extend(parsed_lines(data))
    window=obs['longest_sampled_no_progress']
    pairs=matching_pairs(rows,window['first']['timestamp_ns'],window['last']['timestamp_ns']) if window else []
    qualifying=bool(window and window['span_s']>=120);matches=[p for p in pairs if p['sampled_span_s']>=120] if qualifying else []
    result=dict(kind='evaluation_of_unchanged_registered_hol_metadata_prediction',observation_sha256=sha(observation_path),hypothesis_sha256=sha(hp),
        evaluator_source_sha256=sha(__file__),observed_metadata_matches_registered_conditions=bool(matches),matching_pair_windows=pairs,
        sampled_nonprogress_span_s=window['span_s'] if window else 0,qualifying_120s_nonprogress_window_observed=qualifying,
        conclusion='qualifying_window_not_observed' if not qualifying else 'registered_metadata_conditions_match' if matches else 'registered_conditions_not_matched_in_sampled_window',
        scope='Exact8192-token/<512free/0held/0computed failed-head prediction retained. A later remote holder must already have a received-finish ID and a full-prompt page bound fitting free capacity in same-process adjacent sampled records. Single full-attention group/no-speculation metadata assumption;2s sampling can miss events. A nonmatch is not proof of absence; a match is not a full engine replay, tensor/DMA validation, serving-fix, fairness or performance result. Original root cause and mitigation require source/runtime review and separate intervention.')
    with output.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print('Registered HOL metadata conditions matched:',bool(matches),flush=True);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('observation',type=Path);p.add_argument('output',type=Path);a=p.parse_args();evaluate(a.observation,a.output)
