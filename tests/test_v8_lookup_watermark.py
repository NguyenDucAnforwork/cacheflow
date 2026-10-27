"""Installed method retry bookkeeping, with one-attempt equivalence control."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from v8_lookup_watermark_witness import run


def test_repeated_prefix_is_not_new_stored_data_and_patch_is_not_activated():
    r=run();assert not r['installed_files_modified'] and not r['gpu_execution'] and not r['live_stall_root_cause_proven']
    assert r['cases'][0]['installed']==r['cases'][0]['unactivated_idempotent_prototype']
    assert [c['installed']['prefix_watermark_before_store'] for c in r['cases']]==[1024,2048,8192]
    assert all(c['unactivated_idempotent_prototype']['prefix_watermark_before_store']==1024 for c in r['cases'])
    assert r['unactivated_patch']['replacements']==1
