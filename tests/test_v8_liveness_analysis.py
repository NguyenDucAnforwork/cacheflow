from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v8_analyze_liveness import windows,describe_window,native_window,cohort,PROGRESS


def sample(t,value=1,gpu=0,waiting=9):
    m={k:value for k in PROGRESS};m.update({'vllm:num_requests_running':0,'vllm:num_requests_waiting':waiting,'vllm:kv_cache_usage_perc':.85})
    return dict(timestamp_ns=t*10**9,vllm=m,gpu={'gpu_util_pct':gpu})


def test_progress_and_gpu_break_window_without_high_occupancy_requirement():
    rows=[sample(0),sample(2),sample(4),sample(6,value=2),sample(8,gpu=20),sample(10,value=3),sample(12,value=3)]
    longest,trailing=windows(rows)
    assert [r['timestamp_ns'] for r in longest]==[0,2*10**9,4*10**9]
    assert describe_window(trailing)['span_s']==2
    assert describe_window(longest)['max_sample_gap_s']==2
    assert windows(rows+[sample(14,waiting=0)])[1]==[]


def test_cohort_must_span_entire_observation_and_keeps_unready_state():
    rows=[dict(request_id='a',dispatch_ns=1,complete_ns=100,prefix_group='g',first_token_ns=None),dict(request_id='b',dispatch_ns=50,complete_ns=100,prefix_group='g')]
    result=cohort(rows,10,90)
    assert result['count']==1 and result['requests'][0]['first_token_ns'] is None


def test_native_absent_samples_stay_null_and_never_prove_async_completion():
    result=native_window([dict(kind='allocation_failure',monotonic_ns=1,request_id='a'),dict(kind='allocation_failure',monotonic_ns=20,request_id='b')],0,10)
    assert result['allocation_failures_by_request']=={'a':1}
    assert result['last_scheduler_snapshot'] is None and result['last_worker_snapshot'] is None
    assert result['sampling_can_miss_transient_operations_or_finished_ids'] is True
