"""Distinguish configured-byte parity from effective native allocator capacity."""
import ast
import hashlib
import json
from pathlib import Path
from cacheflow.v4_resources import sglang_host_pool_bytes


def rounded_lazy_bytes(size,chunk):return ((size+chunk-1)//chunk)*chunk


def main():
    root=Path('/venv/main/lib/python3.12/site-packages/lmcache')
    path=root/'v1/memory_allocators/lazy_memory_allocator.py';tree=ast.parse(path.read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LazyMemoryAllocator')
    node=next(n.value for n in cls.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PIN_CHUNK_SIZE' for t in n.targets))
    assert isinstance(node,ast.BinOp) and isinstance(node.op,ast.LShift)
    chunk=ast.literal_eval(node.left)<<ast.literal_eval(node.right);assert chunk==1<<26
    status_path=Path('results/v3/raw/v5r2-confirm-main-union-s702.lmcache-status.json')
    status_blob=status_path.read_bytes();status=json.loads(status_blob)
    actual=status['response']['storage_manager']['l1_manager']['memory_total_bytes']
    native=sglang_host_pool_bytes(16,147456);assert actual==rounded_lazy_bytes(native,chunk)
    rows=[]
    for gb in [16,48]:
        configured=sglang_host_pool_bytes(gb,147456);effective=rounded_lazy_bytes(configured,chunk)
        rows.append(dict(native_host_gb=gb,native_pool_payload_bytes=configured,
            lmcache_configured_budget_bytes=configured,lmcache_lazy_expected_effective_bytes=effective,
            difference_bytes=effective-configured,difference_pct=100*(effective/configured-1),
            observation='Directly observed on current main repeat engine308380/LMCache308252' if gb==16 else 'Source-derived prediction only; full main engine not yet started'))
    sources=['v1/memory_allocators/lazy_memory_allocator.py','v1/distributed/config.py','v1/distributed/l1_manager.py','v1/distributed/memory_manager/l1_memory_manager.py']
    out=dict(scope='Correction: command-line byte roundtrip is not actual cross-engine capacity parity. Existing within-engine policy contrasts remain matched. Do not pool cross-engine timings causally or change sealed current settings.',
        allocator_pin_chunk_bytes=chunk,observed_lmcache_memory_total_bytes=actual,
        status_snapshot_sha256=hashlib.sha256(status_blob).hexdigest(),
        source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in sources},budgets=rows,
        limitations='Historical validation source/argv establishes configured-byte parity only; its effective allocator capacity was not directly snapshotted. Current source predicts rounding for default lazy allocation. Stalled-run root cause is unproven and not attributed to this small host-budget mismatch.')
    Path('results/v3/v5_host_allocator_rounding.json').write_text(json.dumps(out,indent=2)+'\n')
    for r in rows:print(r)


if __name__=='__main__':main()
