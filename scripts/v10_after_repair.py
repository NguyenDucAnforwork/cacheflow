"""Serial V10 development behind exact live V9, preserving its terminal gate."""
import argparse
import json
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
import psutil
from v6_freeze_full import ACTORS,ANALYSIS
from v6_regenerate_full_inputs import wait_parent,idle
from v6_raw_archive import sha
from v10_epoch_study import BASE,PREFIX,PROTOCOL,EXTRA,FREEZE,PROOFS,read,write,prerequisites,freeze
from v10_epoch_plan import build_plan
from v9_native_identity import expected

PARENT=BASE/'v9repair2_registration.json'


def register(pid,path):
    path=Path(path);assert not path.exists() and not FREEZE.exists()
    process=psutil.Process(pid);argv=process.cmdline()
    assert process.is_running() and process.status()!=psutil.STATUS_ZOMBIE
    assert argv[-2:]==['scripts/v9_repair_r1.py','execute']
    parent=read(PARENT)
    from v9_repair_r1 import verify
    verify(parent)
    sources=sorted(set(ACTORS+ANALYSIS+EXTRA))
    evidence={str(p):sha(p) for p in PROOFS.values() if p.exists()}
    registration=dict(kind='serial_v10_epoch_development_after_native_repair',registered_utc=datetime.now(timezone.utc).isoformat(),
        after_pid=pid,after_create_time=process.create_time(),after_argv=argv,parent_registration_sha256=sha(PARENT),
        source_sha256={p:sha(p) for p in sources},protocol_sha256=sha(PROTOCOL),actions=build_plan(),
        available_evidence_sha256=evidence,native_method_expected=expected(),
        scope='Prospective18-arm development only after actual independently audited entire V9six-arm diagnostic with successful probe checks and any full failures retained, retained originalfull failure and revisedCPU proof chain. Fresh engines, native idempotent correction shared by all main baselines/candidates, no native probe.1080targets+1080warmups on60exposedQA. Matched controls and full1986QA/three-seed strongbaseline confirmation remain required.')
    for step in build_plan():
        meta=BASE/'sglang' if step['engine']=='sg' else BASE
        assert not list(meta.glob(step['run_id']+'*'))
    write(path,registration);return registration


def execute(path):
    path=Path(path);r=read(path);out=path.with_suffix('.result.json')
    assert r['kind']=='serial_v10_epoch_development_after_native_repair' and r['actions']==build_plan()
    assert not out.exists() and not path.with_suffix('.failure.json').exists()
    print('V10 waiting on exact V9 controller',r['after_pid'],flush=True)
    wait_parent(r);idle()
    assert sha(PARENT)==r['parent_registration_sha256'] and sha(PROTOCOL)==r['protocol_sha256']
    assert expected()==r['native_method_expected']
    for group in ['source_sha256','available_evidence_sha256']:
        for name,digest in r[group].items():assert sha(name)==digest,name
    prerequisites();freeze()
    subprocess.run([sys.executable,'-u','scripts/v10_epoch_dev.py'],check=True)
    ap=BASE/(PREFIX+'_audit.json');a=read(ap)
    assert a['complete'] is True and a['requests']==1080 and a['errors']==0 and a['separate_warmup_requests']==1080 and a['unique_qa']==60
    assert len(a['runs'])==18 and len(a['primary_pairs'])==12 and len(a['secondary_baseline_diagnostics'])==6 and a['freeze_sha256']==sha(FREEZE)
    write(out,dict(complete_development_pipeline=True,gpu_execution=True,registration_sha256=sha(path),audit_sha256=sha(ap),
        scope='Complete18-arm development only. Preserve regressions; matched controls/fullthree-seed strongbaseline confirmation and research completion audit still required.'))


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('register');c.add_argument('pid',type=int);c.add_argument('output',type=Path)
    c=sub.add_parser('execute');c.add_argument('registration',type=Path);a=p.parse_args()
    if a.command=='register':register(a.pid,a.output);print('Registered serial V10 development',a.output,flush=True)
    else:
        try:execute(a.registration)
        except Exception as exc:
            write(a.registration.with_suffix('.failure.json'),dict(complete=False,error=repr(exc),scope='Retained V10 prerequisite/freeze/execution failure; no retries or successful-only primary claim.'))
            raise
