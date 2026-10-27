from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v8_observe_lookup_watermark import inflated_snapshots


def test_requires_prefetching_zero_scheduled_zero_allocated_and_inflated_watermark():
    def row(state='PREFETCHING',scheduled=0,allocated=None,stored=2048):
        return dict(kind='connector_metadata',pid=7,monotonic_ns=1,tracker_states={'a':dict(state=state,num_scheduled_tokens=scheduled,
            allocated_blocks_per_group=allocated or {},lmcache_hit_tokens=1024,num_stored_tokens=stored)})
    assert inflated_snapshots([row()])[0]['watermark_over_lookup_prefix_ratio']==2
    for r in [row(state='READY'),row(scheduled=1),row(allocated={'0':1}),row(stored=1024)]:assert inflated_snapshots([r])==[]
    assert len(inflated_snapshots([row(),row(stored=8192)]))==1
    assert inflated_snapshots([row(),row(stored=8192)])[0]['tracker']['num_stored_tokens']==8192
