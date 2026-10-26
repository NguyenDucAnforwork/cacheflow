"""Explicit opt-in factory adapter for V6 readiness admission experiments.

Original V5 files stay byte-identical. This process-local dispatch selects new
classes only for new policy names; existing policy constructors remain intact.
The V6 controller must capture this entrypoint and source SHA in its evidence.
"""
from . import v3_memory_scheduler as memory
from .v6_ready_scheduler import ReadyUnionScheduler,ReadyFifoScheduler

READY_POLICIES={'packing_ready','ready_fifo'}


def install_admission_adapter():
    if getattr(memory.ResidencyScheduler,'_cacheflow_v6_adapter',False):return
    parent=memory.ResidencyScheduler
    def dispatch(*,policy,**kwargs):
        if policy=='packing_ready':return ReadyUnionScheduler(policy=policy,**kwargs)
        if policy=='ready_fifo':return ReadyFifoScheduler(policy=policy,**kwargs)
        return parent(policy=policy,**kwargs)
    dispatch._cacheflow_v6_adapter=True
    dispatch._cacheflow_parent=parent
    memory.ResidencyScheduler=dispatch
    memory.RESIDENCY_POLICIES=memory.RESIDENCY_POLICIES|READY_POLICIES
    memory.PURE_PACKING_POLICIES=memory.PURE_PACKING_POLICIES|READY_POLICIES


def create_app():
    install_admission_adapter()
    from .gateway import create_app as original_factory
    return original_factory()
