"""Prospectively pinned serial V7 pipeline, never runs alongside the full study."""
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
from v7_epoch_study import BASE,PREFIX,PROTOCOL,EXTRA,FREEZE,read,write,prerequisites,freeze

PARENT=BASE/'v7_epoch_trace_check_registration.json'


def register(pid,path):
    path=Path(path);assert not path.exists() and not FREEZE.exists()
    process=psutil.Process(pid);argv=process.cmdline()
    assert process.is_running() and process.status()!=psutil.STATUS_ZOMBIE
    assert argv[-3:]==['scripts/v7_epoch_trace_check.py','execute',str(PARENT)]
    sources=sorted(set(ACTORS+ANALYSIS+EXTRA+[__file__]))
    r=dict(kind='serial_v7_development_after_full_cpu_trace_proofs',registered_utc=datetime.now(timezone.utc).isoformat(),
        after_pid=pid,after_create_time=process.create_time(),after_argv=argv,parent_registration_sha256=sha(PARENT),
        source_sha256={p:sha(p) for p in sources},protocol_sha256=sha(PROTOCOL),
        scope='After exact trace-checker exits successfully, require complete originalfull/from-source/namespace/CPU/real-prefix proofs, idle services and all pins; create new seal then execute18fresh-engine development arms1080measured+1080warmup, strict per-run audit/archive and terminal audit. No retries or parallel engines. Not full confirmation or completed research.')
    write(path,r);return r


def execute(path):
    path=Path(path);r=read(path);out=path.with_suffix('.result.json')
    assert r['kind']=='serial_v7_development_after_full_cpu_trace_proofs' and not out.exists() and not path.with_suffix('.failure.json').exists()
    print('V7 waiting on exact real-prefix checker',r['after_pid'],flush=True)
    wait_parent(r);idle()
    assert sha(PARENT)==r['parent_registration_sha256'] and sha(PROTOCOL)==r['protocol_sha256']
    for name,digest in r['source_sha256'].items():assert sha(name)==digest,name
    prerequisites();freeze()
    subprocess.run([sys.executable,'-u','scripts/v7_epoch_dev.py'],check=True)
    audit_path=BASE/(PREFIX+'_audit.json');a=read(audit_path)
    assert a['complete'] is True and a['requests']==1080 and a['errors']==0 and a['separate_warmup_requests']==1080 and a['unique_qa']==60
    assert len(a['runs'])==18 and len(a['primary_pairs'])==12 and len(a['secondary_baseline_diagnostics'])==6 and a['freeze_sha256']==sha(FREEZE)
    write(out,dict(complete_development_pipeline=True,gpu_execution=True,registration_sha256=sha(path),audit_sha256=sha(audit_path),
        scope='Complete18-arm development only; no full confirmation, quality equivalence, universal win or research-goal completion. Preserve all regressions and continue controls/full scaling evaluation.'))


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('register');c.add_argument('pid',type=int);c.add_argument('output',type=Path)
    c=sub.add_parser('execute');c.add_argument('registration',type=Path);a=p.parse_args()
    if a.command=='register':register(a.pid,a.output);print('Registered serial V7 development pipeline',a.output,flush=True)
    else:
        try:execute(a.registration)
        except Exception as exc:
            write(a.registration.with_suffix('.failure.json'),dict(complete=False,error=repr(exc),scope='Preserved V7 prerequisite/freeze/execution failure; no retries or alternate successful-only claim.'))
            raise
