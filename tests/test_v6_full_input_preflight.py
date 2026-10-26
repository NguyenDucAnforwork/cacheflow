import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_full_input_preflight import compare


def fixture():
    return dict(cpu_only=True,complete_trace=True,model_revision='pinned',trace_stored_sha256='stored',trace_uncompressed_sha256='jsonl',trace_canonical_sha256='canonical',tokenizer_artifact_sha256={'config':'hash'},
        page16=dict(requests=2,input_tokens=6),requests=[dict(sample_id='a',qa_index=i,input_tokens=3,max_tokens=96,prompt_sha256='prompt'+str(i),token_ids_u32le_sha256='tokens'+str(i)) for i in range(2)])


def test_full_preflight_compares_token_ids_not_only_lengths():
    a=fixture();b=fixture();assert len(compare(a,b,2))==2
    b['requests'][1]['token_ids_u32le_sha256']='same-length-different-ids'
    with pytest.raises(AssertionError):compare(a,b,2)


def test_partial_trace_missing_semantics_and_changed_tokenizer_are_rejected():
    a=fixture()
    for mutate in [lambda b:b.update(complete_trace=False),lambda b:b['requests'].pop(),
        lambda b:b['requests'][1].update(qa_index=0),lambda b:b['tokenizer_artifact_sha256'].update(config='changed'),
        lambda b:b['requests'][0].update(max_tokens=64)]:
        b=copy.deepcopy(a);mutate(b)
        with pytest.raises(AssertionError):compare(a,b,2)


def test_only_arrival_can_change_in_full_trace_metadata():
    from v6_full_input_preflight import non_arrival_identity
    a=dict(offset_ms=1,prompt='text',group='g',category=1,protocol='p_qa',request_id='r',qa_index=0)
    b=dict(a,offset_ms=123);assert non_arrival_identity(a)==non_arrival_identity(b)
    b['category']=5;assert non_arrival_identity(a)!=non_arrival_identity(b)
