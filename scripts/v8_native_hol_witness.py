"""Conditional native waiting-loop HOL witness, not a live failure reproduction.

Executes the installed waiting-loop prefix through its allocation-failure branch
and installed queue-selection/promotion/allocation methods on CPU fixtures. The
success tail is deliberately replaced by returning the reached candidate. No
serving/native import or installed-source mutation. The skip control is NOT a
complete scheduler patch or a fairness/correctness/performance result.
"""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import MethodType,SimpleNamespace as NS
from v8_allocation_witness import extract,ROOT

SCHED=ROOT/'sched/scheduler.py'


class Queue:
    def __init__(self,requests=()):self.requests=list(requests)
    def __bool__(self):return bool(self.requests)
    def __len__(self):return len(self.requests)
    def peek_request(self):return self.requests[0]
    def pop_request(self):return self.requests.pop(0)
    def prepend_request(self,request):self.requests.insert(0,request)


STATUS=NS(WAITING='WAITING',WAITING_FOR_REMOTE_KVS='WAITING_FOR_REMOTE_KVS',PREEMPTED='PREEMPTED')


def loop_prefix(skip_failure):
    tree=ast.parse(SCHED.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Scheduler')
    schedule=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='schedule')
    loops=[n for n in ast.walk(schedule) if isinstance(n,ast.While) and ast.unparse(n.test)=='(self.waiting or self.skipped_waiting) and token_budget > 0'];assert len(loops)==1
    loop=copy.deepcopy(loops[0]);failure=[i for i,n in enumerate(loop.body) if isinstance(n,ast.If) and ast.unparse(n.test)=='new_blocks is None'];assert len(failure)==1
    stop=failure[0];original=ast.dump(loop,include_attributes=False);loop.body=loop.body[:stop+1]
    if skip_failure:
        branch=loop.body[-1];assert isinstance(branch.body[-1],ast.Break)
        branch.body[-1:]=ast.parse('request_queue.pop_request()\nstep_skipped_waiting.prepend_request(request)\ncontinue').body
    # No downstream model execution/metadata output is simulated. Success only
    # establishes that native guards reached an allocatable later request.
    loop.body+=ast.parse("return dict(request_id=request_id,num_new_tokens=num_new_tokens,status=request.status,deferred_ids=[r.request_id for r in step_skipped_waiting.requests])").body
    node=ast.parse('def fixture_step(self):\n    token_budget=8192\n    encoder_compute_budget=0\n    scheduled_loras=set()\n    step_skipped_waiting=Queue()\n    return None').body[0]
    node.body[-1:-1]=[loop];module=ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[]))
    namespace=dict(Queue=Queue,RequestStatus=STATUS,logger=NS(debug=lambda *a,**kw:None))
    exec(compile(module,str(SCHED)+'::waiting_prefix_cpu_fixture','exec'),namespace)
    return namespace['fixture_step'],dict(native_source_sha256=hashlib.sha256(SCHED.read_bytes()).hexdigest(),
        original_full_waiting_loop_ast_sha256=hashlib.sha256(original.encode()).hexdigest(),
        bound_prefix_ast_sha256=hashlib.sha256(ast.dump(loop,include_attributes=False).encode()).hexdigest(),
        native_first_line=loops[0].lineno,native_prefix_last_line=loops[0].body[stop].end_lineno,
        skip_control=skip_failure,scope='Only native waiting-loop prefix through allocation-failure guard. Success tail replaced by observation return; remaining schedule body, model, worker, queue reinsertion and fairness are not simulated.')


def state(holder_first=False):
    proofs=[]
    def method(path,cls,name,globals_=None):
        fn,proof=extract(path,cls,name,globals_);proofs.append(proof);return fn
    holder=NS(request_id='holder',status=STATUS.WAITING_FOR_REMOTE_KVS,num_computed_tokens=14848,num_tokens=14864,num_preemptions=0,has_encoder_inputs=False)
    head=NS(request_id='head',status=STATUS.WAITING,num_computed_tokens=0,num_tokens=8192,num_preemptions=0,has_encoder_inputs=False,prefill_stats=None)
    held={'head':[],'holder':[NS(block_id=i) for i in range(928)]};pool=NS(free=96);pool.get_num_free_blocks=lambda:pool.free
    manager=NS(block_size=16,_max_admission_blocks_per_request=None,req_to_blocks=held,num_cached_block={'head':0,'holder':928})
    manager.get_num_blocks_to_allocate=MethodType(method(ROOT/'single_type_kv_cache_manager.py','SingleTypeKVCacheManager','get_num_blocks_to_allocate',dict(cdiv=lambda a,b:(a+b-1)//b)),manager)
    coordinator=NS(single_type_managers=[manager]);coordinator.get_num_blocks_to_allocate=MethodType(method(ROOT/'kv_cache_coordinator.py','KVCacheCoordinator','get_num_blocks_to_allocate',dict(CrossAttentionManager=type('Unused',(),{}))),coordinator)
    coordinator.remove_skipped_blocks=lambda *a:None;coordinator.cache_blocks=lambda *a:None
    def allocate_new(rid,num_tokens,*args):
        n=max((num_tokens+15)//16-len(held[rid]),0);assert n<=pool.free
        new=[NS(block_id=10000+i) for i in range(n)];held[rid].extend(new);pool.free-=n;return (new,)
    coordinator.allocate_new_blocks=allocate_new
    cache=NS(coordinator=coordinator,block_pool=pool,empty_kv_cache_blocks=NS(blocks=([],)),max_model_len=32768,enable_caching=True,create_kv_cache_blocks=lambda b:b)
    cache.allocate_slots=MethodType(method(ROOT/'kv_cache_manager.py','KVCacheManager','allocate_slots'),cache)
    cache.get_computed_blocks=lambda req:(cache.empty_kv_cache_blocks,0)
    publications=[];cache.cache_blocks=lambda req,n:publications.append(dict(request_id=req.request_id,tokens=n))
    s=NS(waiting=Queue(),skipped_waiting=Queue([holder,head] if holder_first else [head,holder]),running=[],max_num_running_reqs=16,policy='fcfs',
        lora_config=None,connector=NS(get_num_new_matched_tokens=lambda *a:(0,False)),kv_cache_manager=cache,
        scheduler_config=NS(long_prefill_token_threshold=0,enable_chunked_prefill=True),need_mamba_block_aligned_split=False,
        num_lookahead_tokens=0,is_encoder_decoder=False,scheduler_reserve_full_isl=False,
        failed_recving_kv_req_ids=set(),finished_recving_kv_req_ids={'holder'})
    s._is_blocked_waiting_status=lambda status:status==STATUS.WAITING_FOR_REMOTE_KVS
    s._select_waiting_queue_for_scheduling=MethodType(method(SCHED,'Scheduler','_select_waiting_queue_for_scheduling',dict(SchedulingPolicy=NS(FCFS='fcfs'))),s)
    for name in ['_try_promote_blocked_waiting_request','_update_waiting_for_remote_kv']:
        setattr(s,name,MethodType(method(SCHED,'Scheduler',name,dict(RequestStatus=STATUS)),s))
    return s,pool,held,publications,proofs


def run():
    native,np=loop_prefix(False);skip,sp=loop_prefix(True)
    s,pool,held,published,proofs=state();original=[native(s) for _ in range(3)]
    assert original==[None,None,None] and not published and s.finished_recving_kv_req_ids=={'holder'} and pool.free==96
    s2,p2,h2,pub2,_=state();control=skip(s2)
    assert control['request_id']=='holder' and control['num_new_tokens']==16 and control['deferred_ids']==['head']
    assert pub2==[dict(request_id='holder',tokens=14848)] and not s2.finished_recving_kv_req_ids and p2.free==95
    s3,p3,h3,pub3,_=state(holder_first=True);positive=native(s3);assert positive['request_id']=='holder' and p3.free==95
    return dict(cpu_only=True,synthetic_metadata=True,live_state_reproduced=False,installed_files_modified=False,gpu_execution=False,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),native_method_bodies=proofs,native_prefix=np,unactivated_skip_control=sp,
        usable_blocks=1024,initial_free_blocks=96,head_held_blocks=0,head_first_chunk_tokens=8192,head_first_chunk_blocks=512,
        later_holder_blocks=928,later_holder_computed_tokens=14848,later_holder_new_tokens=16,remote_finish_already_received=True,
        original_three_step_results=original,original_holder_not_promoted=True,skip_control_reached=control,holder_first_positive_control=positive,
        scope='Conditional control-flow witness: a waiting head cannot allocate512pages with96free; native allocation-None break prevents visiting a later928-page holder whose remote-finish ID already arrived and whose16-token suffix fits. Repeated native prefixes leave it unpromoted. A local skip-only control reaches/promotes it; placing holder first also succeeds. Queue order/lookup/cache-publication fixtures are assumptions, not proof of live reachability, complete scheduler correctness, physical tensor validity, fairness, native deadlock cause, a serving fix or speedup. No source patch/import of installed vLLM/torch/CUDA; selected native bodies and truncated waiting-loop prefix only.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args()
    with a.output.open('x') as f:f.write(json.dumps(run(),indent=2)+'\n')
    print('Conditional native waiting-prefix witness; not a live reproduction or serving fix',flush=True)
