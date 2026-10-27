from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v8_native_hol_witness import run


def test_native_head_break_can_hide_already_finished_remote_holder():
    r=run()
    assert r['original_three_step_results']==[None,None,None]
    assert r['original_holder_not_promoted'] and r['remote_finish_already_received']
    assert r['skip_control_reached']['request_id']==r['holder_first_positive_control']['request_id']=='holder'
    assert r['live_state_reproduced'] is False and r['gpu_execution'] is False and r['installed_files_modified'] is False
