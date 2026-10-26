from types import SimpleNamespace as NS
from cacheflow.v5_liveness_probe import scheduler_snapshot,install_scheduler,install_worker


def block(bid,hashed=True):return NS(block_id=bid,ref_cnt=1,block_hash=b'x' if hashed else None,is_null=False)


def scheduler_with_tables(tables):
    requests={rid:NS(status='WAITING_FOR_REMOTE_KVS',block_hashes=[b'common-a',b'common-b'],num_computed_tokens=32,num_tokens=40) for rid in tables}
    blocks={b.block_id:b for table in tables.values() for b in table}
    pool=NS(blocks=list(blocks.values()),get_num_free_blocks=lambda:0)
    manager=NS(block_pool=pool,get_blocks=lambda rid:NS(blocks=(tables[rid],)))
    return NS(requests=requests,kv_cache_manager=manager,running=[],waiting=list(requests),skipped_waiting=[],finished_recving_kv_req_ids=set())


def test_probe_distinguishes_duplicate_pending_copies_from_shared_physical_blocks():
    a,b,c=block(1),block(2,False),block(3,False)
    duplicated=scheduler_snapshot(scheduler_with_tables({'one':[a,b],'two':[a,c]}))
    shared=scheduler_snapshot(scheduler_with_tables({'one':[a,b],'two':[a,b]}))
    assert duplicated['duplicated_expected_prefix_hashes']==1
    assert duplicated['duplicate_physical_blocks_above_one_per_expected_hash']==1
    assert shared['duplicated_expected_prefix_hashes']==0
    assert duplicated['requests'][0]['block_tables'][0]['unhashed']==1
    assert 'common-a' not in str(duplicated)


def test_probe_preserves_scheduler_result_when_snapshot_cannot_be_read(monkeypatch,tmp_path):
    result=object()
    class Scheduler:
        def schedule(self):return result
    module=NS(Scheduler=Scheduler)
    monkeypatch.setenv('CACHEFLOW_VLLM_LIVENESS_LOG',str(tmp_path/'log'))
    install_scheduler(module);first=Scheduler.schedule;install_scheduler(module)
    assert Scheduler.schedule is first and Scheduler().schedule() is result
    assert 'probe_error' in next(tmp_path.iterdir()).read_text()


def test_probe_preserves_worker_result_and_never_queries_pending_future(monkeypatch,tmp_path):
    class NeverQuery:
        def query(self):raise AssertionError('must not poll extra futures')
    result=({'done'},None)
    class LMCacheMPWorkerAdapter:
        is_healthy=True
        store_futures={'pending':NeverQuery()}
        def get_finished(self,finished):return result
    monkeypatch.setenv('CACHEFLOW_VLLM_LIVENESS_LOG',str(tmp_path/'log'))
    module=NS(LMCacheMPWorkerAdapter=LMCacheMPWorkerAdapter);install_worker(module)
    assert LMCacheMPWorkerAdapter().get_finished(set()) is result
    assert 'connector_worker' in next(tmp_path.iterdir()).read_text()


def test_probe_output_failure_does_not_change_native_result(monkeypatch,tmp_path):
    result=object()
    class Scheduler:
        def schedule(self):return result
    parent=tmp_path/'file';parent.write_text('not a directory')
    monkeypatch.setenv('CACHEFLOW_VLLM_LIVENESS_LOG',str(parent/'log'))
    install_scheduler(NS(Scheduler=Scheduler))
    assert Scheduler().schedule() is result


def test_diagnostic_analysis_keeps_missing_native_component_explicit():
    from importlib.util import spec_from_file_location,module_from_spec
    spec=spec_from_file_location('v5_analyze_liveness_probe','scripts/v5_analyze_liveness_probe.py');m=module_from_spec(spec);spec.loader.exec_module(m)
    r=m.summarize([])
    assert not r['both_native_components_observed'] and r['max_duplicate_physical_blocks'] is None
    assert r['max_pending_retrieve_futures'] is None
