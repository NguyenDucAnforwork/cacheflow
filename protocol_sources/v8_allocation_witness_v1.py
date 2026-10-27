"""Conditional CPU feasibility witness, not a live-state/deadlock reproduction.

Execute installed vLLM method bodies with explicit metadata fixtures. No vLLM,
torch or CUDA module is imported. Reachability of the duplicate-loaded-prefix
state in a serving run remains unproven and requires a separate diagnostic.
"""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import MethodType,SimpleNamespace as NS
from cacheflow.scheduler import Ticket
from cacheflow.v3_residency import engine_block_hashes
from cacheflow.v3_memory_scheduler import reserved_tokens

ROOT=Path('/venv/main/lib/python3.12/site-packages/vllm/v1/core')


def extract(path,cls,name,globals_=None):
    text=Path(path).read_text();tree=ast.parse(text)
    owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
    node=copy.deepcopy(next(n for n in owner.body if isinstance(n,ast.FunctionDef) and n.name==name))
    original_ast=ast.dump(node,include_attributes=False);node.decorator_list=[]
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])
    ast.fix_missing_locations(module);scope=dict(globals_ or {});exec(compile(module,str(path),'exec'),scope)
    return scope[name],dict(path=str(path),class_name=cls,method=name,source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        method_ast_sha256=hashlib.sha256(original_ast.encode()).hexdigest(),first_line=node.lineno,
        binding='Original method body; decorators omitted only for binding to CPU fixture, annotations deferred')


def tickets():
    result=[]
    for i in range(2):
        ids=[*range(1024),*range(10000+i*1000,10640+i*1000)];blocks=engine_block_hashes(ids)
        result.append(Ticket(request_id=f'cpu-witness-{i}',blocks=tuple(h.hex() for h in blocks),engine_blocks=blocks,
            arrival_ns=0,enqueued_ns=0,deadline_ns=0,group='shared-1024',input_tokens=len(ids),output_budget=96))
    return result


def run():
    extracted=[]
    def method(file,cls,name,globals_=None):
        fn,proof=extract(ROOT/file,cls,name,globals_);extracted.append(proof);return fn
    get_needed=method('single_type_kv_cache_manager.py','SingleTypeKVCacheManager','get_num_blocks_to_allocate',dict(cdiv=lambda a,b:(a+b-1)//b))
    get_total=method('kv_cache_coordinator.py','KVCacheCoordinator','get_num_blocks_to_allocate',dict(CrossAttentionManager=type('UnusedCrossAttention',(),{})))
    allocate=method('kv_cache_manager.py','KVCacheManager','allocate_slots')
    tt=tickets();capacity_blocks=160;logical=reserved_tokens(tt)//16
    assert logical==158 and logical<=capacity_blocks
    cases=[]
    for duplicated in [True,False]:
        held={t.request_id:[NS(block_id=i+(k*64 if duplicated else 0)) for i in range(64)] for k,t in enumerate(tt)}
        physical={b.block_id for blocks in held.values() for b in blocks};pool=NS(free=capacity_blocks-len(physical));pool.get_num_free_blocks=lambda:pool.free
        manager=NS(block_size=16,_max_admission_blocks_per_request=None,req_to_blocks=held,num_cached_block={t.request_id:64 for t in tt})
        manager.get_num_blocks_to_allocate=MethodType(get_needed,manager)
        coordinator=NS(single_type_managers=[manager]);coordinator.get_num_blocks_to_allocate=MethodType(get_total,coordinator)
        coordinator.remove_skipped_blocks=lambda *args:None  # Full-attention fixture: no sliding-window releases.
        def new_blocks(rid,num_tokens,*args):
            n=max((num_tokens+15)//16-len(held[rid]),0);assert n<=pool.free
            blocks=[NS(block_id=1000+len(held[rid])+i) for i in range(n)];held[rid].extend(blocks);pool.free-=n;return (blocks,)
        coordinator.allocate_new_blocks=new_blocks;coordinator.cache_blocks=lambda *args:None
        cache=NS(coordinator=coordinator,block_pool=pool,empty_kv_cache_blocks=NS(blocks=([],)),max_model_len=32768,enable_caching=True,create_kv_cache_blocks=lambda b:b)
        outcomes=[];initial_free=pool.free
        for t in tt:
            req=NS(request_id=t.request_id,num_computed_tokens=1024,num_tokens=1664)
            before=pool.free;needed=manager.get_num_blocks_to_allocate(req.request_id,1664,[],1024,1664)
            result=allocate(cache,req,num_new_tokens=640)
            outcomes.append(dict(request_id=t.request_id,additional_blocks_needed=needed,free_before=before,allocation_rejected=result is None,free_after=pool.free))
        cases.append(dict(duplicate_physical_prefixes=duplicated,initial_physical_prefix_blocks=len(physical),initial_free_blocks=initial_free,outcomes=outcomes))
    assert all(r['allocation_rejected'] for r in cases[0]['outcomes']) and not any(r['allocation_rejected'] for r in cases[1]['outcomes'])
    return dict(cpu_only=True,synthetic_metadata=True,live_state_reproduced=False,gpu_execution=False,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),native_method_bodies=extracted,
        native_imports_avoided=['vllm','torch','CUDA'],single_full_attention_group=True,tokens_per_page=16,usable_capacity_pages=160,
        logical_union_reservation_pages=logical,shared_prefix_tokens=1024,private_uncached_suffix_tokens_per_request=640,output_budget=96,cases=cases,
        scope='Conditional feasibility counterexample: the real gateway union bound158<=160 pages can admit two prompts, yet if each ready request retains a separate64-page loaded copy of their common prefix, both installed native allocation calls reject40-page suffixes with32free pages. Shared physical prefixes are a positive control. This does not prove such a state occurred/is reachable in the live run, that all asynchronous work has drained, that the scheduler cannot preempt/free waiting requests elsewhere, a native deadlock, a tensor/DMA fault or a fix. Metadata fixtures and selected installed method bodies are not a full engine simulator or serving/performance result.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with a.output.open('x') as f:f.write(json.dumps(run(),indent=2)+'\n')
    print('Conditional CPU allocation witness retained; not a live-state/deadlock reproduction',flush=True)
