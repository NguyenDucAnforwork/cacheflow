"""Nonprogress detector is independent of a near100%KV occupancy assumption."""
import copy
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v7_observe_full_liveness import nonprogress_suffix,parsed_lines,PROGRESS


def samples():
    base=dict(vllm={k:100 for k in PROGRESS},gpu=dict(gpu_util_pct=0))
    base['vllm'].update({'vllm:num_requests_running':0,'vllm:num_requests_waiting':9,'vllm:kv_cache_usage_perc':.918})
    return [dict(copy.deepcopy(base),timestamp_ns=i*1000000000) for i in [0,100,200]]


def test_no99percent_gate_and_progress_or_gpu_activity_breaks_suffix():
    rows=samples();assert len(nonprogress_suffix(rows))==3
    for kind in ['counter','gpu','running','waiting']:
        r=samples()
        if kind=='counter':r[0]['vllm'][PROGRESS[0]]=99
        elif kind=='gpu':r[0]['gpu']['gpu_util_pct']=1
        elif kind=='running':r[0]['vllm']['vllm:num_requests_running']=1
        else:r[0]['vllm']['vllm:num_requests_waiting']=0
        assert len(nonprogress_suffix(r))==2
    rows[-1]['vllm'].pop(PROGRESS[0])
    with pytest.raises(AssertionError):nonprogress_suffix(rows)


def test_only_a_partially_written_final_line_may_be_ignored():
    assert parsed_lines(b'{"a":1}\n{"unfinished"')==[dict(a=1)]
    with pytest.raises(AssertionError):parsed_lines(b'{"unfinished"\n{"a":1}\n')
