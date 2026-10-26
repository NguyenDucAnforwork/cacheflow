"""Opt-in CUDA-event timing of native HiCache MHA layerwise host promotions.

Events are recorded on the real load stream, after its dependency wait. A daemon
polls completion; it never synchronizes the GPU. This does not measure overlap
with model kernels or turn the native CPU enqueue timer into DMA timing.
"""
import functools
import json
import os
import threading
import time
from collections import deque
from pathlib import Path

import torch

_pending=deque()
_lock=threading.Lock()
_worker=None


def _consume():
    path=Path(os.environ['CACHEFLOW_SGLANG_TRANSFER_LOG']);path.parent.mkdir(parents=True,exist_ok=True)
    while True:
        with _lock:
            item=_pending[0] if _pending else None
        if item is not None:
            start,end,metadata=item
            if end.query():
                with _lock:_pending.popleft()
                elapsed=start.elapsed_time(end)
                record=metadata|dict(elapsed_gpu_ms=elapsed,observed_monotonic_ns=time.monotonic_ns(),
                    bandwidth_GB_s=metadata['bytes']/elapsed/1e6 if elapsed>0 else None)
                with path.open('a') as f:f.write(json.dumps(record,sort_keys=True)+'\n')
                continue
        time.sleep(.01)


def install(module):
    cls=module.MHATokenToKVPoolHost
    if getattr(cls,'_cacheflow_transfer_profile_installed',False):return
    original=cls.load_to_device_per_layer
    @functools.wraps(original)
    def timed(self,device_pool,host_indices,device_indices,layer_id,io_backend):
        global _worker
        if layer_id==0:
            if _worker is None:
                _worker=threading.Thread(target=_consume,daemon=True,name='cacheflow-transfer-events');_worker.start()
            start=torch.cuda.Event(enable_timing=True);start.record(torch.cuda.current_stream())
            self._cacheflow_transfer_start=(start,dict(pid=os.getpid(),phase='H2D',
                tokens=host_indices.numel(),bytes=host_indices.numel()*2*self.layer_num*
                self.device_pool.head_num*self.device_pool.head_dim*self.dtype.itemsize,
                layers=self.layer_num,layout=self.layout,io_backend=io_backend,
                launch_monotonic_ns=time.monotonic_ns()))
        result=original(self,device_pool,host_indices,device_indices,layer_id,io_backend)
        if layer_id==self.layer_num-1:
            end=torch.cuda.Event(enable_timing=True);end.record(torch.cuda.current_stream())
            start,metadata=self._cacheflow_transfer_start
            with _lock:_pending.append((start,end,metadata))
            self._cacheflow_transfer_start=None
        return result
    cls.load_to_device_per_layer=timed
    cls._cacheflow_transfer_profile_installed=True
