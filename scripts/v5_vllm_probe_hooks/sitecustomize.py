"""Separate diagnostic-only native introspection; upstream files stay unchanged."""
import importlib.abc
import importlib.machinery
import os
import sys

if os.environ.get('CACHEFLOW_VLLM_LIVENESS_LOG'):
    class ProbeFinder(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            targets={'vllm.v1.core.sched.scheduler':'install_scheduler',
                     'lmcache.integration.vllm.vllm_multi_process_adapter':'install_worker'}
            if fullname not in targets:return None
            spec=importlib.machinery.PathFinder.find_spec(fullname,path)
            if spec is None:return None
            original=spec.loader
            class Loader:
                def create_module(self,spec):return original.create_module(spec)
                def exec_module(self,module):
                    original.exec_module(module)
                    from cacheflow import v5_liveness_probe
                    getattr(v5_liveness_probe,targets[fullname])(module)
                def __getattr__(self,name):return getattr(original,name)
            spec.loader=Loader();return spec
    sys.meta_path.insert(0,ProbeFinder())
