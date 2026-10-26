"""Opt-in import hook for CUDA transfer timing; original upstream source stays intact."""
import importlib.abc
import importlib.machinery
import os
import sys

profile=os.environ.get('CACHEFLOW_SGLANG_TRANSFER_PROFILE')=='1'
guard=os.environ.get('CACHEFLOW_SG_SAME_BATCH_GUARD')=='1'
if profile or guard:
    class TransferFinder(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            targets={'sglang.srt.managers.schedule_policy'}
            if profile:targets.update({'sglang.srt.mem_cache.memory_pool_host','sglang.srt.mem_cache.hiradix_cache'})
            if fullname not in targets:return None
            spec=importlib.machinery.PathFinder.find_spec(fullname,path)
            if spec is None:return None
            original=spec.loader
            class Loader:
                def create_module(self,spec):return original.create_module(spec)
                def exec_module(self,module):
                    original.exec_module(module)
                    if guard and fullname.endswith('schedule_policy'):
                        from cacheflow.v4_sglang_delayhit import install as install_guard
                        install_guard(module)
                    if not profile:return
                    if fullname.endswith('memory_pool_host'):
                        from cacheflow.v3_sglang_transfer_profile import install
                    else:
                        from cacheflow.v4_sglang_admission_profile import install
                    install(module)
                def __getattr__(self,name):return getattr(original,name)
            spec.loader=Loader()
            return spec
    sys.meta_path.insert(0,TransferFinder())
