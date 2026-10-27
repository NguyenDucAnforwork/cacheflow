"""Prepared, opt-in epoch/reference factory; never installs on module import.

The historical banner in the pinned CPU prototype predates this entrypoint.
Existing V6 launchers/factory and all running serving processes are unchanged.
Implementation must be selected explicitly in each new gateway process; changing
it in an already-patched process is rejected. No GPU study is launched here.
"""
import hashlib
import os
from pathlib import Path
from . import v3_memory_scheduler as memory

IMPLEMENTATIONS={'reference','epoch'}
EPOCH_POLICIES={'packing_reuse','packing_ready','ready_fifo'}


def install_admission_adapter(implementation):
    if implementation not in IMPLEMENTATIONS:raise ValueError('Explicit reference/epoch implementation required')
    parent=memory.ResidencyScheduler
    if getattr(parent,'_cacheflow_v7_adapter',False):
        if parent._cacheflow_implementation!=implementation:raise RuntimeError('Cannot switch implementation in an existing gateway process')
        return
    if not isinstance(parent,type):raise RuntimeError('Require a fresh process without another admission adapter')
    from .v6_ready_scheduler import ReadyUnionScheduler,ReadyFifoScheduler
    constructors={'packing_reuse':parent,'packing_ready':ReadyUnionScheduler,'ready_fifo':ReadyFifoScheduler}
    if implementation=='epoch':
        from .v7_epoch_scheduler import EpochUnionScheduler,EpochReadyUnionScheduler,EpochReadyFifoScheduler
        constructors={'packing_reuse':EpochUnionScheduler,'packing_ready':EpochReadyUnionScheduler,'ready_fifo':EpochReadyFifoScheduler}
    def dispatch(*,policy,**kwargs):
        if policy in constructors:return constructors[policy](policy=policy,**kwargs)
        if implementation=='epoch':raise ValueError('Epoch implementation does not support policy: '+policy)
        return parent(policy=policy,**kwargs)
    dispatch._cacheflow_v7_adapter=True
    dispatch._cacheflow_parent=parent
    dispatch._cacheflow_implementation=implementation
    memory.ResidencyScheduler=dispatch
    memory.RESIDENCY_POLICIES=memory.RESIDENCY_POLICIES|EPOCH_POLICIES
    memory.PURE_PACKING_POLICIES=memory.PURE_PACKING_POLICIES|EPOCH_POLICIES


def create_app(config_path=None):
    implementation=os.environ.get('CACHEFLOW_SCHEDULER_IMPLEMENTATION')
    install_admission_adapter(implementation)
    from .gateway import create_app as original_factory
    app=original_factory(config_path);scheduler=app.state.scheduler
    # Hash once at construction, outside measurement. A later GET returns the
    # captured record rather than hashing changed on-disk files retrospectively.
    paths=[Path(__file__),Path(__file__).with_name('v7_epoch_scheduler.py'),
        Path(__file__).with_name('v6_ready_scheduler.py'),Path(__file__).with_name('v3_memory_scheduler.py'),
        Path(__file__).with_name('scheduler.py'),Path(__file__).with_name('gateway.py')]
    selector=getattr(scheduler,'_uncached_selector',scheduler._choose)
    record=dict(implementation=implementation,policy=scheduler.policy,
        scheduler_class=type(scheduler).__module__+'.'+type(scheduler).__qualname__,
        selector=selector.__func__.__module__+'.'+selector.__func__.__qualname__,
        source_sha256={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        scope='Factory construction identity only; not proof of a registered GPU run, completed replay, performance, quality or equivalence.')
    app.state.scheduler_implementation_record=record
    @app.get('/implementation')
    async def implementation_identity():return record
    return app
