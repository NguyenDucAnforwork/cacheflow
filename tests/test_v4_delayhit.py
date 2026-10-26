from array import array
from types import SimpleNamespace
from cacheflow.v4_sglang_delayhit import duplicate_producer,install


def request(tokens,cached=0,host=0,extend=None):
    return SimpleNamespace(origin_input_ids=array('q',tokens),prefix_indices=[0]*cached,
        host_hit_length=host,extend_input_len=len(tokens)-cached if extend is None else extend)


def test_partial_prefix_duplicate_is_deferred_but_ready_or_distinct_work_is_not():
    ids=list(range(15000))
    producer=request([*ids,99],cached=13280,extend=1721)
    follower=request([*ids,100],cached=13280)
    assert duplicate_producer(follower,[producer]) is producer
    assert duplicate_producer(request([*ids,100],cached=14900),[producer]) is None
    assert duplicate_producer(request([*ids,100],cached=13280,host=1720),[producer]) is None
    different=request([*range(100),*range(20000,34900)],cached=13280)
    assert duplicate_producer(different,[producer]) is None


def test_guard_only_defers_more_than_threshold_and_within_selected_chunk():
    ids=list(range(16000))
    producer=request(ids,cached=12000,extend=2000)
    assert duplicate_producer(request(ids,cached=13899),[producer]) is producer
    assert duplicate_producer(request(ids,cached=13900),[producer]) is None
    assert duplicate_producer(request(ids,cached=14000),[producer]) is None
    other=request(ids,cached=12000);other.extra_key='other-adapter'
    assert duplicate_producer(other,[producer]) is None
    hybrid=request(ids,cached=12000);hybrid.mamba_pool_idx=5
    assert duplicate_producer(hybrid,[producer]) is None


def test_native_wrapper_keeps_follower_queued_and_admits_complementary_work():
    class Adder:
        def __init__(self):self.can_run_list=[]
        def add_one_req(self,req):self.can_run_list.append(req);return 'continue'
    module=SimpleNamespace(PrefillAdder=Adder,AddReqResult=SimpleNamespace(CONTINUE='continue'))
    install(module);install(module)
    adder=Adder();a=request(list(range(16000)),cached=12000,extend=2000)
    b=request(list(range(16000)),cached=12000)
    c=request(list(range(50000,66000)),cached=12000)
    assert adder.add_one_req(a)=='continue'
    assert adder.add_one_req(b)=='continue' and b not in adder.can_run_list
    assert adder.add_one_req(c)=='continue' and c in adder.can_run_list
    next_batch=Adder()
    b.prefix_indices=[0]*14000
    assert next_batch.add_one_req(b)=='continue' and b in next_batch.can_run_list
