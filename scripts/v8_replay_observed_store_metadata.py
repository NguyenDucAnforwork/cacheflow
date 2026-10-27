"""Native STORE method on observed scalar bounds; dummy payload/constructors.

No live method call, tensor, CUDA or backend STORE is issued. The reduced
token-list length is a recent lower bound, not the original payload. This can
establish a conditional metadata opportunity, not lost unique cache bytes.
"""
import hashlib
import json
from pathlib import Path
from types import MethodType,SimpleNamespace as NS
from v6_raw_archive import sha
from v7_observe_full_liveness import parsed_lines
from v8_allocation_witness import extract

SOURCE=Path('/venv/main/lib/python3.12/site-packages/lmcache/integration/vllm/lmcache_mp_connector.py')


def candidates(rows):
    latest={};found={}
    for row in sorted(rows,key=lambda r:r['monotonic_ns']):
        if row['kind']=='scheduler':
            for request in row['requests']:latest[row['pid'],request['request_id']]=(row['monotonic_ns'],request)
        elif row['kind']=='connector_metadata':
            for rid,t in row['tracker_states'].items():
                if t['state']!='READY' or t['num_stored_tokens']<=32768 or len(t['allocated_blocks_per_group'])!=1:continue
                preceding=latest.get((row['pid'],rid))
                if preceding is None or row['monotonic_ns']-preceding[0]>2_500_000_000:continue
                token_bound=preceding[1]['num_tokens'];allocated=t['allocated_blocks_per_group'].get('0',0)*16
                available=min(token_bound,allocated,t['num_scheduled_tokens']+max(t['vllm_hit_tokens'],t['lmcache_hit_tokens']))
                tokens=(available-t['lmcache_hit_tokens'])//256*256
                if tokens<=0:continue
                if rid not in found or tokens>found[rid]['conditional_eligible_store_tokens']:
                    found[rid]=dict(request_id=rid,pid=row['pid'],monotonic_ns=row['monotonic_ns'],
                        preceding_scheduler_ns=preceding[0],token_list_length_lower_bound=token_bound,tracker=t,
                        available_tokens_lower_bound=available,conditional_eligible_store_tokens=tokens)
    return list(found.values())


def replay_scalar_store(case,stored):
    def slice_blocks(allocated,sizes,start,end):return {g:ids[start//sizes[g]:end//sizes[g]] for g,ids in allocated.items()}
    store,proof=extract(SOURCE,'LMCacheMPRequestMetadata','GetStoreMetadata',dict(slice_block_ids_per_group=slice_blocks,LoadStoreOp=lambda **kw:NS(**kw),LMCacheMPRequestMetadata=lambda **kw:NS(**kw)))
    increment,_=extract(SOURCE,'LMCacheMPRequestTracker','increase_num_stored_tokens')
    t=case['tracker'];length=case['token_list_length_lower_bound'];blocks={int(k):list(range(v)) for k,v in t['allocated_blocks_per_group'].items()}
    fixture=NS(request_id=case['request_id'],cache_salt='',all_token_ids=range(length),allocated_block_ids=blocks,
        num_stored_tokens=stored,num_scheduled_tokens=t['num_scheduled_tokens'],num_vllm_hit_tokens=t['vllm_hit_tokens'],num_lmcache_hit_tokens=t['lmcache_hit_tokens'])
    fixture.num_allocated_blocks=lambda:{k:len(v) for k,v in blocks.items()};fixture.get_token_ids=lambda:list(range(length))
    fixture.increase_num_stored_tokens=MethodType(increment,fixture)
    metadata=store(fixture,256,[16])
    return None if metadata is None else dict(direction=metadata.direction,start=metadata.op.start,end=metadata.op.end),proof


def main():
    base=Path('results/v3');out=base/'v8diag3_observed_store_metadata_replay_01.json';assert not out.exists()
    reg_path=base/'v8diag3_registration.json';reg=json.loads(reg_path.read_text());assert sha(SOURCE)==reg['native_source_sha256'][str(SOURCE)]
    rows=[];prefixes=[]
    for path in sorted((base/'raw').glob('v8diag3-probe.*.jsonl')):
        blob=path.read_bytes();rows.extend(parsed_lines(blob));prefixes.append(dict(path=str(path),prefix_bytes=len(blob),prefix_sha256=hashlib.sha256(blob).hexdigest()))
    cases=candidates(rows);assert cases,'No observed READY candidate with a conservative eligible span'
    proof=None
    for case in cases:
        observed,proof=replay_scalar_store(case,case['tracker']['num_stored_tokens'])
        lower,_=replay_scalar_store(case,case['tracker']['lmcache_hit_tokens'])
        assert observed is None and lower is not None and lower['end']-lower['start']==case['conditional_eligible_store_tokens']
        case.update(installed_method_with_observed_watermark=observed,conditional_method_with_lookup_prefix_watermark=lower)
    result=dict(kind='native_store_metadata_replay_on_observed_scalar_bounds',diagnostic_only=True,performance_valid=False,
        registration_sha256=sha(reg_path),journal_prefixes=prefixes,source_sha256=sha(__file__),native_method=proof,
        distinct_observed_request_ids=len(cases),cases=cases,
        scope='Actual profiled READY tracker/scalar counts joined to a preceding same-process request token-length lower bound within2.5s, under pinned non-speculative single full-attention Qwen. Installed STORE method executed only on CPU fixtures with dummy tokens/block IDs/metadata constructors. Inflated watermark returnsNone; setting only that fixture watermark to cached-prefix length exposes eligible256-aligned ranges. Not an actual backend STORE/RPC, tensor correctness, missed unique bytes, cache residency, performance/quality effect, full counterfactual request history, stall root cause or activated fix. Samples and request IDs are diagnostic observations, not complete incidence.')
    out.write_text(json.dumps(result,indent=2)+'\n');print('Observed scalar STORE candidates:',len(cases),'largest eligible span',max(c['conditional_eligible_store_tokens'] for c in cases),'tokens',flush=True)


if __name__=='__main__':main()
