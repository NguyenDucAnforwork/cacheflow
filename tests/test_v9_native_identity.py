from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import sys
from types import CodeType,FunctionType,ModuleType,SimpleNamespace as NS
import pytest
from cacheflow.v9_lookup_watermark import install
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import v9_native_identity as identity


@pytest.mark.parametrize('mode',['reference','idempotent'])
def test_prospective_fingerprints_match_actual_bound_native_body_without_native_import(monkeypatch,tmp_path,mode):
    wanted=identity.expected();source=identity.SOURCE;module_code=compile(source.read_text(),str(source),'exec')
    cls_code=next(c for c in module_code.co_consts if isinstance(c,CodeType) and c.co_name=='LMCacheMPConnector')
    method_code=next(c for c in cls_code.co_consts if isinstance(c,CodeType) and c.co_name=='get_num_new_matched_tokens')
    native=ModuleType('lmcache.integration.vllm.lmcache_mp_connector');native.__file__=str(source)
    native.logger=NS(debug=lambda *a:None);native.RequestStatus=NS(PREEMPTED='PREEMPTED')
    fn=FunctionType(method_code,vars(native))
    class KVConnectorRole(Enum):SCHEDULER=1;WORKER=2
    def initialize(self,role):self.role=role
    cls=type('LMCacheMPConnector',(),{'__module__':native.__name__,'__init__':initialize,'get_num_new_matched_tokens':fn});native.LMCacheMPConnector=cls
    monkeypatch.chdir(tmp_path);prefix=str(tmp_path/'results/v3/raw/test-proof')
    install(native,mode,prefix,hashlib.sha256(source.read_bytes()).hexdigest());cls(KVConnectorRole.SCHEDULER);cls(KVConnectorRole.WORKER)
    env=dict(CACHEFLOW_V9_WATERMARK_MODE=mode,CACHEFLOW_V9_ENABLE_PROBE='0',CACHEFLOW_V9_WATERMARK_PROOF=prefix)
    fake=NS(pid=os.getpid(),is_running=lambda:True,status=lambda:'running',create_time=lambda:123,environ=lambda:env,children=lambda recursive:[])
    monkeypatch.setattr(identity.psutil,'Process',lambda pid:fake)
    result=identity.identity(dict(mode=mode,probe=False,proof_label='test-proof'),dict(pid=os.getpid(),birth=123),dict(native_method_expected=wanted))
    assert len(result['constructor_records'])==2 and result['end_identity_verified']
    row=result['constructor_records'][0];assert row['effective_method_code_sha256']==wanted[mode]['effective_method_code_sha256']
    wanted[mode]['effective_method_code_sha256']='tampered'
    with pytest.raises(AssertionError):identity.identity(dict(mode=mode,probe=False,proof_label='test-proof'),dict(pid=os.getpid(),birth=123),dict(native_method_expected=wanted))
