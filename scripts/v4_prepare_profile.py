"""CPU-only event-loop responsiveness experiment on exact dev prompt sizes."""
import asyncio
import hashlib
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
import numpy as np
from transformers import AutoTokenizer
from cacheflow.v2_replay import load_trace
from cacheflow.v4_prepare import prepare
from cacheflow.prefix import prefix_blocks
from cacheflow.v3_residency import engine_block_hashes
from v3_model import get_model


async def measure(tok,rows,model,thread):
    gaps=[];stop=False;outputs=[];timings=[]
    async def heartbeat():
        last=time.perf_counter()
        while not stop:
            await asyncio.sleep(.001);now=time.perf_counter();gaps.append((now-last)*1000);last=now
    beat=asyncio.create_task(heartbeat());await asyncio.sleep(.01)
    pool=ThreadPoolExecutor(max_workers=1) if thread else None
    start=time.perf_counter()
    try:
        for row in rows:
            work=partial(prepare,tok,row.prompt,256,model['path'],True)
            result=await asyncio.get_running_loop().run_in_executor(pool,work) if pool else work()
            outputs.append(result[:3]);timings.append(result[3]);await asyncio.sleep(0)
    finally:
        elapsed=time.perf_counter()-start;stop=True;await beat
        if pool:pool.shutdown()
    return outputs,dict(mode='serial_worker' if thread else 'inline',wall_s=elapsed,
        heartbeat_gap_p50_ms=float(np.percentile(gaps,50)),heartbeat_gap_p99_ms=float(np.percentile(gaps,99)),
        heartbeat_gap_max_ms=max(gaps),tokenize_mean_ms=statistics.mean(t['tokenize_ms'] for t in timings),
        hash_mean_ms=statistics.mean(t['prefix_hash_ms'] for t in timings))


async def main():
    model=get_model('qwen3-4b');tok=AutoTokenizer.from_pretrained(model['path'],local_files_only=True)
    rows=load_trace(Path('data/processed/v3/v4-dev4b3-qps4-s101.jsonl'))[:20]
    inline,im=await measure(tok,rows,model,False);worker,wm=await measure(tok,rows,model,True)
    assert inline==worker
    for row,(ids,blocks,engine) in zip(rows,worker):
        assert len(ids)==row.input_tokens
        assert ids==tok.encode(row.prompt,add_special_tokens=False)
        assert blocks==prefix_blocks(ids,block_size=256,namespace=model['path'])
        assert engine==engine_block_hashes(ids)
    Path('results/v3/prepare_eventloop_profile.json').write_text(json.dumps(dict(
        scope='CPU-only saturated preparation of20 real dev prompts,1ms heartbeat; no GPU/E2E speedup claim; single worker avoids concurrent tokenizer mutation',
        model_revision=model['revision'],requests=len(rows),exact_ids_and_both_hashes_equal=True,
        source_sha256=hashlib.sha256(Path('src/cacheflow/v4_prepare.py').read_bytes()).hexdigest(),runs=[im,wm]),indent=2)+'\n')
    print(im);print(wm)


if __name__=='__main__':asyncio.run(main())
