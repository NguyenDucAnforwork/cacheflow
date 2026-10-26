"""Opt-in import hook for CUDA transfer timing; original upstream source stays intact."""
import importlib.abc
import importlib.machinery
import os
import sys

if os.environ.get('CACHEFLOW_SGLANG_TRANSFER_PROFILE')=='1':
    class TransferFinder(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if fullname!='sglang.srt.mem_cache.memory_pool_host':return None
            spec=importlib.machinery.PathFinder.find_spec(fullname,path)
            if spec is None:return None
            original=spec.loader
            class Loader:
                def create_module(self,spec):return original.create_module(spec)
                def exec_module(self,module):
                    original.exec_module(module)
                    from cacheflow.v3_sglang_transfer_profile import install
                    install(module)
                def __getattr__(self,name):return getattr(original,name)
            spec.loader=Loader()
            return spec
    sys.meta_path.insert(0,TransferFinder())
