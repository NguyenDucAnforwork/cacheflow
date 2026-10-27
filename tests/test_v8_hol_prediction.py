from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v8_evaluate_hol_prediction import matching_pairs


def rows(finished=True,new_tokens=8192):
    result=[]
    for t in [1,131_000_000_001]:
        result.append(dict(kind='allocation_failure',pid=7,monotonic_ns=t,request_id='head',computed_tokens=0,held_blocks_per_group=[0],free_blocks_after=96,arguments={'num_new_tokens':new_tokens}))
        result.append(dict(kind='scheduler',pid=7,monotonic_ns=t+1,free_blocks=96,finished_recving_kv_req_ids=['holder'] if finished else [],
            requests=[dict(request_id='head',status='WAITING',num_computed_tokens=0),dict(request_id='holder',status='WAITING_FOR_REMOTE_KVS',num_computed_tokens=14848,num_tokens=14864,block_tables=[{'allocated':928}])]))
    return result


def test_requires_same_head_finished_holder_and_registered_token_count():
    pairs=matching_pairs(rows(),0,140_000_000_000)
    assert len(pairs)==1 and pairs[0]['sampled_span_s']==131 and pairs[0]['last']['holder_additional_full_prompt_pages']==1
    assert matching_pairs(rows(finished=False),0,140_000_000_000)==[]
    assert matching_pairs(rows(new_tokens=4096),0,140_000_000_000)==[]


def test_stale_or_other_process_failure_is_not_joined_to_scheduler():
    data=rows();data[0]['pid']=8;data[2]['pid']=8
    assert matching_pairs(data,0,140_000_000_000)==[]
    data=rows();data[1]['monotonic_ns']+=3_000_000_000;data[3]['monotonic_ns']+=3_000_000_000
    assert matching_pairs(data,0,140_000_000_000)==[]
