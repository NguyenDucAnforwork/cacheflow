"""CPU-only prompt preparation, usable on the event loop or a serial worker."""
import time
from .prefix import prefix_blocks
from .v3_residency import engine_block_hashes


def prepare(tokenizer,prompt,block_size,namespace,need_engine_blocks):
    start=time.monotonic_ns();cpu=time.thread_time_ns()
    ids=tokenizer.encode(prompt,add_special_tokens=False)
    encoded=time.monotonic_ns()
    blocks=prefix_blocks(ids,block_size=block_size,namespace=namespace)
    engine=engine_block_hashes(ids) if need_engine_blocks else ()
    end=time.monotonic_ns()
    return ids,blocks,engine,dict(start_ns=start,tokenize_ms=(encoded-start)/1e6,
        prefix_hash_ms=(end-encoded)/1e6,cpu_ms=(time.thread_time_ns()-cpu)/1e6)
