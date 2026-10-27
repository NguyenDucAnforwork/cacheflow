"""CPU-only native lookup-retry watermark witness and unactivated correction.

No installed file is modified and no native engine, torch or CUDA is imported.
This identifies a conditional bookkeeping issue, not the live stall's cause.
"""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import MethodType,SimpleNamespace as NS
from v8_allocation_witness import extract

SOURCE=Path('/venv/main/lib/python3.12/site-packages/lmcache/integration/vllm/lmcache_mp_connector.py')


def corrected_lookup():
    tree=ast.parse(SOURCE.read_text());owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LMCacheMPConnector')
    node=copy.deepcopy(next(n for n in owner.body if isinstance(n,ast.FunctionDef) and n.name=='get_num_new_matched_tokens'));node.decorator_list=[]
    class Replace(ast.NodeTransformer):
        count=0
        def visit_Expr(self,n):
            value=n.value
            if isinstance(value,ast.Call) and isinstance(value.func,ast.Attribute) and ast.unparse(value.func)=='tracker.increase_num_stored_tokens' and len(value.args)==1 and ast.unparse(value.args[0])=='ret':
                self.count+=1;return ast.copy_location(ast.parse('tracker.num_stored_tokens=max(tracker.num_stored_tokens,ret)').body[0],n)
            return self.generic_visit(n)
    patch=Replace();node=patch.visit(node);assert patch.count==1,'Unexpected installed lookup body'
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[]);ast.fix_missing_locations(module)
    scope=dict(RequestStatus=NS(PREEMPTED='PREEMPTED'),logger=NS(debug=lambda *a:None));exec(compile(module,'unactivated_idempotent_lookup','exec'),scope)
    return scope[node.name],dict(replacements=1,corrected_method_ast_sha256=hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest(),
        change='Only lookup watermark update: additive cached-prefix count becomes max(current,ret). Other incremental store updates remain unchanged.')


def run():
    globals_=dict(RequestStatus=NS(PREEMPTED='PREEMPTED'),logger=NS(debug=lambda *a:None))
    original,lookup_proof=extract(SOURCE,'LMCacheMPConnector','get_num_new_matched_tokens',globals_)
    increment,increment_proof=extract(SOURCE,'LMCacheMPRequestTracker','increase_num_stored_tokens')
    def slice_blocks(allocated,sizes,start,end):return {g:ids[start//sizes[g]:end//sizes[g]] for g,ids in allocated.items()}
    store,store_proof=extract(SOURCE,'LMCacheMPRequestMetadata','GetStoreMetadata',dict(slice_block_ids_per_group=slice_blocks,LoadStoreOp=lambda **k:NS(**k),LMCacheMPRequestMetadata=lambda **k:NS(**k)))
    fixed,patch=corrected_lookup();cases=[]
    for attempts in [1,2,8]:
        row=dict(lookup_attempts_before_successful_allocation=attempts)
        for name,fn in [('installed',original),('unactivated_idempotent_prototype',fixed)]:
            t=NS(num_stored_tokens=0,num_scheduled_tokens=0,num_vllm_hit_tokens=0,num_lmcache_hit_tokens=0,cache_salt='',request_id='cpu-watermark',
                allocated_block_ids={0:list(range(104))},all_token_ids=list(range(1664)))
            t.get_token_ids=lambda:list(range(1664));t.increase_num_stored_tokens=MethodType(increment,t);t.num_allocated_blocks=lambda:{0:104}
            adapter=NS(maybe_submit_lookup_request=lambda *a,**k:None,check_lookup_result=lambda rid:1024,lmcache_tokens_per_chunk=256)
            connector=NS(_get_or_create_request_tracker=lambda request:t,scheduler_adapter=adapter,_hit_alignment_tokens=16)
            request=NS(request_id=t.request_id,status='WAITING');values=[]
            for _ in range(attempts):values.append(fn(connector,request,0))
            assert values==[(1024,True)]*attempts
            before_store=t.num_stored_tokens;t.num_scheduled_tokens=640
            metadata=store(t,256,[16]);span=None if metadata is None else dict(direction=metadata.direction,start=metadata.op.start,end=metadata.op.end)
            row[name]=dict(prefix_watermark_before_store=before_store,store_metadata_after640new_tokens=span)
        cases.append(row)
    assert cases[0]['installed']==cases[0]['unactivated_idempotent_prototype']
    for c in cases[1:]:
        assert c['installed']['store_metadata_after640new_tokens'] is None
        assert c['unactivated_idempotent_prototype']['store_metadata_after640new_tokens']==dict(direction='STORE',start=1024,end=1536)
    return dict(cpu_only=True,synthetic_metadata=True,installed_files_modified=False,gpu_execution=False,live_stall_root_cause_proven=False,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),native_method_bodies=[lookup_proof,increment_proof,store_proof],unactivated_patch=patch,cases=cases,
        scope='Execute installed method bodies on a conditional same-request lookup retry before allocation succeeds. Each lookup returns the same cached1024-token prefix; additive watermark grows to2048/8192 on2/8attempts and suppresses an otherwise eligible512-token STORE after640newtokens. A one-site unactivated max-watermark change preserves the first-attempt result. Metadata constructors and single-group slicing are CPU fixtures. This is not proof the retries occurred in the live run, actual lost cache data/bytes/quality/performance, the stall root cause or a validated serving fix. No engine, model, torch, CUDA or installed-file mutation.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with a.output.open('x') as f:f.write(json.dumps(run(),indent=2)+'\n')
    print('Conditional native lookup-watermark witness retained; no live root-cause claim',flush=True)
