"""Diagnostic wrappers preserve results and avoid added polls/table mutations."""
from collections import defaultdict
import json
from types import SimpleNamespace as NS
import pytest
from cacheflow import v8_liveness_probe as probe


def tracker():return NS(state=NS(name='PREFETCHING'),num_vllm_hit_tokens=0,num_lmcache_hit_tokens=1024,num_stored_tokens=2048,num_scheduled_tokens=0,allocated_block_ids={0:[]})


def test_scheduler_snapshot_does_not_create_missing_defaultdict_tables():
    block=NS(block_id=1,ref_cnt=1,is_null=False,block_hash=None);tables=defaultdict(list,{'a':[block]})
    manager=NS(coordinator=NS(single_type_managers=[NS(req_to_blocks=tables)]),block_pool=NS(blocks=[block],get_num_free_blocks=lambda:32))
    request=lambda:NS(status=NS(name='WAITING'),block_hashes=[b'common'],num_computed_tokens=0,num_tokens=1664)
    adapter=NS(_pending_lookups={'b'},_finished_lookup_results={'a':1024},_per_server_hits={})
    scheduler=NS(kv_cache_manager=manager,connector=NS(request_trackers={'a':tracker()},scheduler_adapter=adapter),requests={'a':request(),'b':request()},
        running=[],waiting=['a','b'],skipped_waiting=[],finished_recving_kv_req_ids=set())
    r=probe.scheduler_snapshot(scheduler)
    assert set(tables)=={'a'} and r['requests'][1]['block_tables'][0]['allocated']==0
    assert r['requests'][0]['connector_tracker']['num_stored_tokens']==2048 and r['lookup_membership']['_pending_lookups']['first_ids']==['b']


def logs(tmp_path):return [json.loads(l) for p in tmp_path.glob('*.jsonl') for l in p.read_text().splitlines()]


def test_allocator_keeps_none_and_records_failed_arguments_without_extra_allocation(monkeypatch,tmp_path):
    monkeypatch.setenv('CACHEFLOW_V8_LIVENESS_LOG',str(tmp_path/'probe'))
    class KVCacheManager:
        calls=0
        coordinator=NS(single_type_managers=[NS(req_to_blocks={'a':list(range(64))})])
        block_pool=NS(get_num_free_blocks=lambda:32)
        def allocate_slots(self,request,num_new_tokens,num_new_computed_tokens=0,new_computed_blocks=None,num_lookahead_tokens=0,num_external_computed_tokens=0,delay_cache_blocks=False,num_encoder_tokens=0,full_sequence_must_fit=False):
            self.calls+=1;return None
    probe.install_allocator(NS(KVCacheManager=KVCacheManager));first=KVCacheManager.allocate_slots;probe.install_allocator(NS(KVCacheManager=KVCacheManager))
    assert KVCacheManager.allocate_slots is first
    m=KVCacheManager();r=NS(request_id='a',status=NS(name='WAITING'),num_computed_tokens=1024,num_tokens=1664)
    assert m.allocate_slots(r,640) is None and m.calls==1
    row=next(r for r in logs(tmp_path) if r['kind']=='allocation_failure')
    assert row['free_blocks_after']==32 and row['held_blocks_per_group']==[64] and row['arguments']['num_new_tokens']==640


def test_worker_membership_does_not_query_future_or_cuda_event(monkeypatch,tmp_path):
    monkeypatch.setenv('CACHEFLOW_V8_LIVENESS_LOG',str(tmp_path/'probe'))
    class NeverQuery:
        def query(self):raise AssertionError('No extra queries')
        def result(self,*a,**kw):raise AssertionError('No added blocking')
    result=({'sent'},{'received'})
    class LMCacheMPWorkerAdapter:
        store_futures={'a':NeverQuery()};retrieve_futures={'b':NeverQuery()};store_events={'a':NeverQuery()};retrieve_events={'b':NeverQuery()};_dropped_retrieves=set();is_healthy=True
        def get_finished(self,finished):return result
    probe.install_worker(NS(LMCacheMPWorkerAdapter=LMCacheMPWorkerAdapter))
    assert LMCacheMPWorkerAdapter().get_finished(set()) is result
    row=next(r for r in logs(tmp_path) if r['kind']=='connector_worker');assert row['state']['retrieve_futures']['count']==1


def test_connector_preserves_metadata_and_never_serializes_tokens(monkeypatch,tmp_path):
    monkeypatch.setenv('CACHEFLOW_V8_LIVENESS_LOG',str(tmp_path/'probe'))
    result=NS(requests=[NS(request_id='a',direction='RETRIEVE',op=NS(start=0,end=1024,skip_first_n_tokens=16,token_ids=['SECRET-PROMPT']))])
    class LMCacheMPConnector:
        request_trackers={'a':tracker()}
        def build_connector_meta(self,output):return result
    probe.install_connector(NS(LMCacheMPConnector=LMCacheMPConnector));assert LMCacheMPConnector().build_connector_meta(None) is result
    rows=logs(tmp_path);assert any(r['kind']=='connector_metadata' for r in rows) and 'SECRET-PROMPT' not in str(rows)


def test_sampling_attribute_or_snapshot_output_failure_cannot_change_native_result(monkeypatch,tmp_path):
    result=object();monkeypatch.setenv('CACHEFLOW_V8_LIVENESS_LOG',str(tmp_path/'probe'))
    class Scheduler:
        __slots__=()
        def schedule(self):return result
    probe.install_scheduler(NS(Scheduler=Scheduler));assert Scheduler().schedule() is result
    assert any(r['kind']=='probe_error' for r in logs(tmp_path))
    file=tmp_path/'not-a-directory';file.write_text('x');monkeypatch.setenv('CACHEFLOW_V8_LIVENESS_LOG',str(file/'probe'))
    assert Scheduler().schedule() is result


def test_original_exception_still_propagates(monkeypatch,tmp_path):
    monkeypatch.setenv('CACHEFLOW_V8_LIVENESS_LOG',str(tmp_path/'probe'))
    class Scheduler:
        def schedule(self):raise RuntimeError('native failure')
    probe.install_scheduler(NS(Scheduler=Scheduler))
    with pytest.raises(RuntimeError,match='native failure'):Scheduler().schedule()
