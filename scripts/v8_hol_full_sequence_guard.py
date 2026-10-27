"""Conditional HOL prefix check with both full-sequence guard settings."""
import hashlib
import json
from pathlib import Path
from v8_native_hol_witness import loop_prefix,state


def run():
    native,np=loop_prefix(False);skip,sp=loop_prefix(True);cases=[]
    for reserve_full in [False,True]:
        s,pool,held,published,_=state();s.scheduler_reserve_full_isl=reserve_full
        outcomes=[native(s) for _ in range(3)]
        assert outcomes==[None,None,None] and not published and pool.free==96 and s.finished_recving_kv_req_ids=={'holder'}
        control,free,_,publications,_=state();control.scheduler_reserve_full_isl=reserve_full;reached=skip(control)
        assert reached['request_id']=='holder' and reached['num_new_tokens']==16 and free.free==95
        cases.append(dict(full_sequence_must_fit=reserve_full,original_step_results=outcomes,skip_control_reached=reached,
            skip_control_publications=publications,final_free_blocks=free.free))
    return dict(cpu_only=True,synthetic_metadata=True,live_state_reproduced=False,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        witness_source_sha256=hashlib.sha256(Path('scripts/v8_native_hol_witness.py').read_bytes()).hexdigest(),native_prefix=np,unactivated_control=sp,cases=cases,
        scope='Supplement after early profiled native samples showed full_sequence_must_fit=True. Same conditional CPU fixture with both flag values; not a changed prospective prediction, live engine-state/reachability proof, complete scheduler, installed fix or performance result.')


if __name__=='__main__':
    path=Path('results/v3/v8_hol_full_sequence_guard.json');assert not path.exists();path.write_text(json.dumps(run(),indent=2)+'\n')
