"""Reopen a failed full native intervention ledger and locate fatal assertion.

This binds an observed engine traceback to the installed source, not to the
preceding stall's cause, the identity of the missing request, or a proposed fix.
"""
import argparse
import ast
import json
import re
from pathlib import Path
from v6_raw_archive import sha
from v8_diagnostic_capture import check_rows
from v7_observe_full_liveness import parsed_lines
from v9_repair_r1 import REG,verify

BASE=Path('results/v3');RAW=BASE/'raw'
SCHEDULER=Path('/venv/main/lib/python3.12/site-packages/vllm/v1/core/sched/scheduler.py')


def fatal_site(text,source_path):
    lines={int(n) for n in re.findall(re.escape(str(source_path))+r'", line (\d+), in _update_from_kv_xfer_finished',text)}
    assert len(lines)==1,'No unique observed native failure frame'
    line=lines.pop();tree=ast.parse(source_path.read_text());matches=[]
    for fn in ast.walk(tree):
        if isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)) and fn.name=='_update_from_kv_xfer_finished':
            for loop in ast.walk(fn):
                if isinstance(loop,ast.For):
                    for assertion in ast.walk(loop):
                        if isinstance(assertion,ast.Assert) and assertion.lineno==line:
                            matches.append(dict(method=fn.name,line=line,loop_iterator=ast.unparse(loop.iter),assertion=ast.unparse(assertion.test)))
    assert len(matches)==1 and 'AssertionError' in text
    return matches[0]


def audit(run_id,liveness_path,output):
    output=Path(output);assert not output.exists();reg=json.loads(REG.read_text());verify(reg)
    step=next(s for s in reg['actions'] if s['run_id']==run_id);assert step['stage']=='full' and not step['probe']
    read=lambda path:json.loads(Path(path).read_text())
    setup_path=BASE/(run_id+'.diagnostic_setup.json');setup=read(setup_path)
    integrity_path=BASE/(run_id+'.diagnostic_integrity.json');integrity=read(integrity_path)
    identity_path=BASE/(run_id+'.native_identity.json');identity=read(identity_path)
    ap=BASE/(run_id+'.repair_audit.json');a=read(ap);outcome=read(BASE/(run_id+'.outcome.json'))
    assert setup['step']==a['step']==step and outcome['audit_sha256']==sha(ap)
    assert a['result']==dict(integrity,native_identity_sha256=sha(identity_path))
    assert setup['registration_sha256']==integrity['registration_sha256']==identity['registration_sha256']==a['registration_sha256']==sha(REG)
    assert identity['setup_sha256']==integrity['setup_sha256']==sha(setup_path)
    for name,digest in integrity['raw_sha256'].items():assert sha(name)==digest,name
    summary=read(RAW/(run_id+'.summary.json'));assert summary['requests']==1986 and summary['errors']>0
    assert summary['request_read_timeout_s']==summary['request_pool_timeout_s']==600 and summary['client_keepalive_connections']==0
    assert summary['engine_pid']==setup['engine']['pid']==identity['before']['engine_pid']
    assert summary['lmcache_pid']==setup['lmcache']['pid']
    pre=read(BASE/'v6full1_input_preflight.json');fp=Path(pre['main_fingerprints_path']);assert sha(fp)==pre['main_fingerprints_sha256']
    expected={r['request_id']:r for r in read(fp)['requests']}
    rows=parsed_lines((RAW/(run_id+'.jsonl')).read_bytes());outputs=parsed_lines((RAW/(run_id+'.outputs.jsonl')).read_bytes())
    statuses=check_rows(rows,outputs,expected,run_id)
    assert len(rows)==1986 and statuses==integrity['status_counts'] and statuses['ok']==summary['successes'] and 1986-statuses['ok']==summary['errors']
    for proof in identity['before']['constructor_records']:
        for key,value in reg['native_method_expected'][step['mode']].items():assert proof[key]==value,key
    for name,digest in identity['before']['proof_sha256'].items():assert sha(name)==digest,name
    assert a['quality_sha256'] is None and not (BASE/(run_id+'.quality.json')).exists()
    log=Path(a['engine_log_path']);assert sha(log)==a['engine_log_sha256'];text=log.read_text()
    assert sha(SCHEDULER)==reg['native_source_sha256'][str(SCHEDULER)]
    site=fatal_site(text,SCHEDULER)
    liveness_path=Path(liveness_path);live=read(liveness_path)
    assert live['run_id']==run_id and live['terminal_client_result'] and live['client_outcome']=={k:summary[k] for k in ['requests','successes','errors']}
    assert live['summary_sha256']==sha(RAW/(run_id+'.summary.json')) and live['registration_sha256']==sha(REG)
    result=dict(kind='independent_failed_native_full_ledger_and_traceback_audit',run_id=run_id,
        complete_failed_workload_ledger_audit=True,performance_valid=False,research_complete=False,
        requests=1986,successes=summary['successes'],errors=summary['errors'],status_counts=statuses,
        terminal_finished_utc=summary['finished_utc'],native_mode=step['mode'],native_fatal_site=site,
        missing_native_request_id=None,engine_end_identity_verified=identity['after']['end_identity_verified'],
        longest_sampled_nonprogress_s=live['longest_sampled_no_progress']['span_s'],closed_gateway_cohort=live['closed_gateway_cohort'],
        raw_sha256=integrity['raw_sha256']|{str(log):sha(log)},
        metadata_sha256={str(p):sha(p) for p in [REG,setup_path,integrity_path,identity_path,ap,fp,liveness_path]},
        native_scheduler_source_sha256=sha(SCHEDULER),auditor_source_sha256=sha(__file__),
        scope='All1986statuses/outputs/prompt-token fingerprints reopened, actual native startup identity and failed missing end identity retained. Fatal traceback maps to installed assertion in a finished-transfer loop. No missing req_id value is logged; no proof that cancellation caused the earlier sampled stall, unique causal chain, functional mitigation, partial-cohort quality or successful-only latency claim.')
    with output.open('x') as out:out.write(json.dumps(result,indent=2)+'\n')
    print('Failed full ledger independently audited',json.dumps({k:result[k] for k in ['requests','successes','errors','longest_sampled_nonprogress_s','native_fatal_site']}),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument('liveness',type=Path);p.add_argument('output',type=Path);a=p.parse_args();audit(a.run_id,a.liveness,a.output)
