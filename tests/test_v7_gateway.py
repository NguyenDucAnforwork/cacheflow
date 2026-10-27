"""Fresh-process CPU integration and opt-in contracts, no serving engine."""
import os
import subprocess
import sys
from pathlib import Path
import pytest


def run(code):
    subprocess.run([sys.executable,'-c',code],check=True,env=dict(os.environ,PYTHONPATH='src'))


def test_import_does_not_patch_and_missing_mode_fails_before_tokenizer_or_config():
    run('''
import os
from cacheflow import v3_memory_scheduler as m
parent=m.ResidencyScheduler
from cacheflow.v7_gateway import create_app
assert m.ResidencyScheduler is parent
for mode in [None,'typo','EPOCH']:
 if mode is None:os.environ.pop('CACHEFLOW_SCHEDULER_IMPLEMENTATION',None)
 else:os.environ['CACHEFLOW_SCHEDULER_IMPLEMENTATION']=mode
 try:create_app('/nonexistent/config')
 except ValueError:pass
 else:raise AssertionError('Missing/invalid mode accepted')
 assert m.ResidencyScheduler is parent
''')


@pytest.mark.parametrize('mode',['reference','epoch'])
def test_explicit_modes_keep_policy_and_selector_and_cannot_flip_in_one_process(mode):
    run('''
from cacheflow import v3_memory_scheduler as m
from cacheflow.v3_residency import ResidencyIndex
from cacheflow.v7_gateway import install_admission_adapter
from cacheflow.v6_ready_scheduler import ReadyUnionScheduler,ReadyFifoScheduler
parent=m.ResidencyScheduler
mode=%r
install_admission_adapter(mode);adapter=m.ResidencyScheduler;install_admission_adapter(mode)
assert m.ResidencyScheduler is adapter
expected={'packing_reuse':parent,'packing_ready':ReadyUnionScheduler,'ready_fifo':ReadyFifoScheduler}
for policy,cls in expected.items():
 s=m.ResidencyScheduler(policy=policy,residency_index=ResidencyIndex(),kv_capacity_tokens=4096)
 assert s.policy==policy
 if mode=='reference':assert type(s) is cls
 else:assert s._uncached_selector.__func__ is (cls._choose_impl if policy=='packing_reuse' else cls._choose_ready)
try:install_admission_adapter('epoch' if mode=='reference' else 'reference')
except RuntimeError:pass
else:raise AssertionError('Runtime mode switch allowed')
if mode=='epoch':
 try:m.ResidencyScheduler(policy='lpm_real',residency_index=ResidencyIndex(),kv_capacity_tokens=4096)
 except ValueError:pass
 else:raise AssertionError('Unsupported epoch policy accepted')
''' % mode)


def test_prior_v6_adapter_is_rejected_instead_of_changing_its_existing_process():
    run('''
from cacheflow.v6_gateway import install_admission_adapter as v6
v6()
from cacheflow.v7_gateway import install_admission_adapter
try:install_admission_adapter('epoch')
except RuntimeError:pass
else:raise AssertionError('V6 process was silently patched')
''')


def test_launcher_diff_is_only_explicit_mode_gate_and_new_factory():
    old=Path('scripts/v6_serve_gateway.sh').read_text()
    new=Path('scripts/v7_serve_gateway.sh').read_text()
    start=new.index('# A separate marker');end=new.index('mkdir -p',start)
    stripped=new[:start]+new[end:]
    assert stripped==old.replace('cacheflow.v6_gateway:create_app','cacheflow.v7_gateway:create_app')
    subprocess.run(['bash','-n','scripts/v7_serve_gateway.sh'],check=True)


@pytest.mark.parametrize('mode',['reference','epoch'])
def test_actual_factory_and_diagnostic_routes_with_fake_tokenizer_no_weights(tmp_path,mode):
    # Run in a fresh process: patching a constructor in the test runner would
    # contaminate other independent reference/prototype tests.
    run('''
import os,json,tempfile
from pathlib import Path
os.environ['CACHEFLOW_SCHEDULER_IMPLEMENTATION']=%r
os.environ['CACHEFLOW_POLICY']='packing_ready'
os.environ['CACHEFLOW_TRACE']=%r
from cacheflow import gateway
gateway.AutoTokenizer.from_pretrained=lambda *a,**k:object()
from cacheflow.v7_gateway import create_app
path=Path(%r)
path.write_text('model: fake-local-model\\nscheduler:\\n  policy: packing_ready\\nresidency:\\n  enabled: false\\n  kv_capacity_tokens: 4096\\n')
app=create_app(str(path))
from fastapi.testclient import TestClient
with TestClient(app) as client:
 health=client.get('/health').json();identity=client.get('/implementation').json()
 assert health['queue']==health['active']==0 and health['policy']=='packing_ready'
 assert identity['implementation']==%r
 assert identity['selector']=='cacheflow.v6_ready_scheduler.ReadyUnionScheduler._choose_ready' if %r=='epoch' else identity['selector']=='cacheflow.v6_ready_scheduler.ReadyUnionScheduler._choose'
 assert identity['source_sha256'] and identity==app.state.scheduler_implementation_record
 assert ('Epoch' in identity['scheduler_class'])==(%r=='epoch')
''' % (mode,str(tmp_path/'trace.jsonl'),str(tmp_path/'config.yaml'),mode,mode,mode))
