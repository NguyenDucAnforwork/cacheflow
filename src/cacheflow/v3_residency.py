"""Track real GPU KV residency from vLLM's public KV-event stream."""
from __future__ import annotations

import asyncio
import hashlib
import pickle
import time
from collections import Counter


def engine_block_hashes(token_ids, block_size=16, seed='0'):
    """Pinned vLLM sha256 hash contract, text-only/no salt/LoRA; protocol 5 on Py3.12."""
    parent=hashlib.sha256(pickle.dumps(seed,protocol=pickle.HIGHEST_PROTOCOL)).digest()
    out=[]
    for start in range(0,len(token_ids)-block_size+1,block_size):
        parent=hashlib.sha256(pickle.dumps((parent,tuple(token_ids[start:start+block_size]),None),
            protocol=pickle.HIGHEST_PROTOCOL)).digest()
        out.append(parent)
    return tuple(out)


class ResidencyIndex:
    def __init__(self):
        self.refs=Counter()
        self.known=False
        self.last_sequence=None
        self.gaps=0
        self.last_event_ns=None
        self.batches=0
        self.events=0

    def apply(self,sequence,events):
        if self.last_sequence is not None and sequence!=self.last_sequence+1:
            self.refs.clear();self.known=False;self.gaps+=1
        self.last_sequence=sequence;self.batches+=1
        self.last_event_ns=time.monotonic_ns()
        for event in events:
            self.events+=1
            kind=type(event).__name__
            if kind=='AllBlocksCleared':
                self.refs.clear();self.known=True
            elif getattr(event,'medium',None) not in (None,'GPU'):
                continue
            elif getattr(event,'group_idx',0) not in (None,0):
                continue
            elif kind=='BlockStored':
                self.refs.update(event.block_hashes)
            elif kind=='BlockRemoved':
                for key in event.block_hashes:
                    if self.refs[key]>1:self.refs[key]-=1
                    else:self.refs.pop(key,None)

    def matched_tokens(self,blocks,block_size=16):
        if not self.known:return 0
        for i,key in enumerate(blocks):
            if key not in self.refs:return i*block_size
        return len(blocks)*block_size

    def stats(self):
        return dict(known=self.known,sequence=self.last_sequence,gaps=self.gaps,
            blocks=len(self.refs),events=self.events,batches=self.batches,
            last_event_age_ms=(time.monotonic_ns()-self.last_event_ns)/1e6 if self.last_event_ns else None)


class ResidencySubscriber:
    def __init__(self,index,endpoint='tcp://127.0.0.1:5557'):
        self.index=index;self.endpoint=endpoint;self.task=None;self.socket=None
        self.hash_contract_verified=False

    async def run(self):
        import msgspec
        import zmq
        import zmq.asyncio
        from vllm.distributed.kv_events import KVEventBatch
        self.socket=zmq.asyncio.Context.instance().socket(zmq.SUB)
        self.socket.setsockopt(zmq.SUBSCRIBE,b'')
        self.socket.setsockopt(zmq.RCVHWM,100000)
        self.socket.connect(self.endpoint)
        decoder=msgspec.msgpack.Decoder(type=KVEventBatch)
        try:
            while True:
                frames=await self.socket.recv_multipart()
                if len(frames)!=3:continue
                seq=int.from_bytes(frames[1],'big')
                batch=decoder.decode(frames[2])
                if not self.hash_contract_verified:
                    for event in batch.events:
                        if type(event).__name__ == 'BlockStored' and event.block_hashes and event.medium == 'GPU':
                            verify_event_hash_contract(event)
                            self.hash_contract_verified=True
                            break
                self.index.apply(seq,batch.events)
        except Exception:
            self.index.known=False
            raise
        finally:
            self.socket.close(linger=0)

    def start(self):self.task=asyncio.create_task(self.run())

    def stats(self):
        failed = self.task is not None and self.task.done() and not self.task.cancelled()
        error = self.task.exception() if failed else None
        return self.index.stats() | {'subscriber_running': self.task is not None and not self.task.done(),
                                   'hash_contract_verified': self.hash_contract_verified,
                                   'subscriber_error': repr(error) if error else None}

    async def close(self):
        if self.task:
            self.task.cancel()
            try:await self.task
            except asyncio.CancelledError:pass


def verify_event_hash_contract(event):
    """Validate an actual store payload before using the external hash namespace."""
    if event.block_size != 16 or not isinstance(event.block_hashes[0], bytes):
        raise ValueError('expected 16-token blocks and byte hashes; set VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=0')
    parent=event.parent_block_hash
    if parent is None:
        parent=hashlib.sha256(pickle.dumps('0',protocol=pickle.HIGHEST_PROTOCOL)).digest()
    extra=getattr(event,'extra_keys',None)
    first_extra=extra[0] if extra else None
    actual=hashlib.sha256(pickle.dumps((parent,tuple(event.token_ids[:16]),first_extra),
        protocol=pickle.HIGHEST_PROTOCOL)).digest()
    if actual != event.block_hashes[0] or first_extra is not None:
        raise ValueError('event hash contract differs from the supported text-only/no-salt namespace')
