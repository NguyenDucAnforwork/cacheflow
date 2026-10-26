import sys
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_input_oracle import minimum_work


def test_prefix_blocks_are_causal_not_global_payload_deduplication():
    r=minimum_work([[1,2,5,6],[3,4,5,6]],2)
    assert r['distinct_complete_causal_blocks']==4 and r['input_only_minimum_new_tokens']==8


def test_shared_complete_block_private_tails_and_order_invariance():
    rows=[[1,2,3],[1,2,4],[1,2,3,5]]
    a=minimum_work(rows,2);b=minimum_work(reversed(rows),2)
    assert a==b and a['private_partial_tail_tokens']==2
    assert a['distinct_complete_causal_blocks']==2 and a['input_only_minimum_new_tokens']==6
    assert minimum_work(rows,1)['input_only_minimum_new_tokens']==5
