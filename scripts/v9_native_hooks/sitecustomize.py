"""Opt-in native correction/identity and optional diagnostic-only metadata."""
import importlib.abc
import importlib.machinery
import os
import sys

mode=os.environ.get('CACHEFLOW_V9_WATERMARK_MODE')
if mode:
    if mode not in {'reference','idempotent'}:raise RuntimeError('Unknown native watermark implementation')
    probe=os.environ.get('CACHEFLOW_V9_ENABLE_PROBE','0')
    if probe not in {'0','1'}:raise RuntimeError('Explicit V9 probe boolean required')
    if bool(os.environ.get('CACHEFLOW_V8_LIVENESS_LOG'))!=(probe=='1'):raise RuntimeError('Probe/log configuration mismatch')
    if os.environ.get('CACHEFLOW_VLLM_LIVENESS_LOG'):raise RuntimeError('Do not mix legacy native hooks')
    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            connector='lmcache.integration.vllm.lmcache_mp_connector'
            targets={connector:'install_connector'}
            if probe=='1':targets.update({'vllm.v1.core.sched.scheduler':'install_scheduler','vllm.v1.core.kv_cache_manager':'install_allocator',
                'lmcache.integration.vllm.vllm_multi_process_adapter':'install_worker'})
            if fullname not in targets:return None
            spec=importlib.machinery.PathFinder.find_spec(fullname,path)
            if spec is None:return None
            original=spec.loader
            class Loader:
                def create_module(self,spec):return original.create_module(spec)
                def exec_module(self,module):
                    original.exec_module(module)
                    if fullname==connector:
                        from cacheflow.v9_lookup_watermark import install
                        install(module,mode,os.environ['CACHEFLOW_V9_WATERMARK_PROOF'],os.environ['CACHEFLOW_V9_EXPECTED_CONNECTOR_SHA'])
                    if probe=='1':
                        from cacheflow import v8_liveness_probe
                        getattr(v8_liveness_probe,targets[fullname])(module)
                def __getattr__(self,name):return getattr(original,name)
            spec.loader=Loader();return spec
    sys.meta_path.insert(0,Finder())
