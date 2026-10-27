import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType,MethodType,SimpleNamespace as NS
import pytest
from cacheflow.v9_lookup_watermark import corrected_node,method_node,install
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v8_allocation_witness import extract

SOURCE=Path('/venv/main/lib/python3.12/site-packages/lmcache/integration/vllm/lmcache_mp_connector.py')


def fixture():
    m=ModuleType('native_fixture');m.__file__=str(SOURCE)
    globals_=dict(RequestStatus=NS(PREEMPTED='PREEMPTED'),logger=NS(debug=lambda *a:None))
    original,_=extract(SOURCE,'LMCacheMPConnector','get_num_new_matched_tokens',globals_)
    increment,_=extract(SOURCE,'LMCacheMPRequestTracker','increase_num_stored_tokens')
    tracker=NS(request_id='r',cache_salt='',num_stored_tokens=0,num_scheduled_tokens=0,num_vllm_hit_tokens=0,num_lmcache_hit_tokens=0,get_token_ids=lambda:[0]*1664)
    tracker.increase_num_stored_tokens=MethodType(increment,tracker)
    adapter=NS(maybe_submit_lookup_request=lambda *a,**kw:None,check_lookup_result=lambda rid:1024,lmcache_tokens_per_chunk=256)
    def initialize(self):self.scheduler_adapter=adapter;self._hit_alignment_tokens=16;self._get_or_create_request_tracker=lambda r:tracker
    cls=type('LMCacheMPConnector',(),{'__init__':initialize,'get_num_new_matched_tokens':original});m.LMCacheMPConnector=cls;m.__dict__.update(globals_)
    return m,tracker,adapter


def test_patch_is_exactly_one_expression_and_reversible():
    source=SOURCE.read_text();node,proof=corrected_node(source);assert proof['replacements']==1
    class Undo(ast.NodeTransformer):
        count=0
        def visit_Assign(self,n):
            if ast.unparse(n)=='tracker.num_stored_tokens = max(tracker.num_stored_tokens, ret)':
                self.count+=1;return ast.copy_location(ast.parse('tracker.increase_num_stored_tokens(ret)').body[0],n)
            return self.generic_visit(n)
    undo=Undo();restored=undo.visit(copy.deepcopy(node));assert undo.count==1
    assert ast.dump(restored,include_attributes=False)==ast.dump(method_node(source),include_attributes=False)
    with pytest.raises(AssertionError):corrected_node(source.replace('tracker.increase_num_stored_tokens(ret)','tracker.increase_num_stored_tokens(ret+1)'))


@pytest.mark.parametrize('mode,expected',[('reference',8192),('idempotent',1024)])
def test_actual_constructor_proof_and_repeated_lookup_identity(tmp_path,mode,expected):
    m,t,a=fixture();install(m,mode,str(tmp_path/'proof'),hashlib.sha256(SOURCE.read_bytes()).hexdigest())
    first=m.LMCacheMPConnector.get_num_new_matched_tokens;install(m,mode,str(tmp_path/'proof'),hashlib.sha256(SOURCE.read_bytes()).hexdigest());assert first is m.LMCacheMPConnector.get_num_new_matched_tokens
    c=m.LMCacheMPConnector();request=NS(request_id='r',status='WAITING')
    assert [c.get_num_new_matched_tokens(request,0) for _ in range(8)]==[(1024,True)]*8 and t.num_stored_tokens==expected
    proof=json.loads(next(tmp_path.glob('proof.*.jsonl')).read_text());assert proof['mode']==mode and proof['functional_replacements']==int(mode=='idempotent')
    with pytest.raises(RuntimeError):install(m,'reference' if mode=='idempotent' else 'idempotent',str(tmp_path/'proof'),'unused')


def test_real_store_increments_preserved_and_lookup_return_paths_unchanged(tmp_path):
    m,t,a=fixture();install(m,'idempotent',str(tmp_path/'proof'),hashlib.sha256(SOURCE.read_bytes()).hexdigest());c=m.LMCacheMPConnector();request=NS(request_id='r',status='WAITING')
    assert c.get_num_new_matched_tokens(request,0)==(1024,True);t.increase_num_stored_tokens(640)
    assert c.get_num_new_matched_tokens(request,0)==(1024,True) and t.num_stored_tokens==1664
    for value,result in [(None,(None,True)),(0,(0,False))]:
        a.check_lookup_result=lambda rid:value;before=t.num_stored_tokens;assert c.get_num_new_matched_tokens(request,0)==result and t.num_stored_tokens==before
    a.check_lookup_result=lambda rid:1024
    assert c.get_num_new_matched_tokens(request,1031)==(0,False) and t.num_vllm_hit_tokens==1024
    request.status='PREEMPTED';assert c.get_num_new_matched_tokens(request,0)==(0,False)


def test_native_exception_and_source_drift_fail_closed(tmp_path):
    m,t,a=fixture()
    with pytest.raises(AssertionError,match='Unexpected installed'):install(m,'idempotent',str(tmp_path/'proof'),'wrong')
    assert not hasattr(m.LMCacheMPConnector,'_cacheflow_v9_watermark_mode')
    install(m,'idempotent',str(tmp_path/'proof'),hashlib.sha256(SOURCE.read_bytes()).hexdigest());c=m.LMCacheMPConnector()
    def fail(rid):raise LookupError('native lookup failed')
    a.check_lookup_result=fail
    with pytest.raises(LookupError,match='native lookup failed'):c.get_num_new_matched_tokens(NS(request_id='r',status='WAITING'),0)
