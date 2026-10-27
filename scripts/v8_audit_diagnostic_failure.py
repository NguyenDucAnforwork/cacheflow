"""Postmortem whole-client-ledger audit when the original collector stopped."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from v6_raw_archive import sha
from v7_observe_full_liveness import parsed_lines
from v8_diagnostic_capture import check_rows


def audit(output):
    base=Path('results/v3');raw=base/'raw';rid='v8diag1-offA-target';output=Path(output);assert not output.exists()
    reg_path=base/'v8diag1_registration.json';reg=json.loads(reg_path.read_text());step=next(s for s in reg['actions'] if s['run_id']==rid)
    setup_path=base/(rid+'.diagnostic_setup.json');setup=json.loads(setup_path.read_text());assert setup['step']==step and setup['registration_sha256']==sha(reg_path)
    terminal_path=base/'v8diag1_terminal.json';terminal=json.loads(terminal_path.read_text());assert terminal['diagnostic_execution_complete'] is False and terminal['cleanup_errors']==[]
    assert len(terminal['outcomes'])==1 and terminal['outcomes'][0]['run_id']=='v8diag1-offA-warm'
    summary_path=raw/(rid+'.summary.json');summary=json.loads(summary_path.read_text())
    assert summary['requests']==1986 and summary['errors']>0 and summary['engine_pid']==setup['engine']['pid']
    assert summary['request_read_timeout_s']==summary['request_pool_timeout_s']==600 and summary['client_keepalive_connections']==0
    manifest_path=Path(step['trace']).with_suffix('.manifest.json');manifest=json.loads(manifest_path.read_text());assert summary['trace_sha256']==manifest['trace_sha256']
    pre=json.loads((base/'v6full1_input_preflight.json').read_text());fp=Path(pre['main_fingerprints_path']);assert sha(fp)==pre['main_fingerprints_sha256']
    expected={r['request_id']:r for r in json.loads(fp.read_text())['requests']}
    rp=raw/(rid+'.jsonl');op=raw/(rid+'.outputs.jsonl');rows=parsed_lines(rp.read_bytes());outputs=parsed_lines(op.read_bytes())
    statuses=check_rows(rows,outputs,expected,rid);assert statuses.get('ok',0)==summary['successes'] and len(rows)-statuses.get('ok',0)==summary['errors']
    log_path=raw/'gateway.jsonl';blob=log_path.read_bytes();gate=[r for r in parsed_lines(blob) if r.get('run_id')==rid];ids={r['request_id'] for r in gate}
    assert len(ids)==len(gate) and ids<=expected.keys() and {r['request_id'] for r in rows if r['status']=='ok'}<=ids
    supervisor=Path('/var/log/supervisor/supervisord.log');sb=supervisor.read_bytes();events=[l for l in sb.decode().splitlines() if l.startswith('2026-10-27 03:12:34') and 'exited: cacheflow_v2_vllm (exit status 0; expected)' in l];assert len(events)==1
    files=[rp,op,summary_path,raw/(rid+'.metrics.jsonl')]
    result=dict(kind='postmortem_client_record_integrity_after_collector_failure',run_id=rid,diagnostic_only=True,performance_valid=False,
        requests=1986,successes=summary['successes'],errors=summary['errors'],status_counts=statuses,
        gateway_closed_records=len(gate),missing_closed_gateway_records=len(expected.keys()-ids),gateway_status_counts=dict(Counter(r['status'] for r in gate)),
        raw_sha256={str(p):sha(p) for p in files},metadata_sha256={str(p):sha(p) for p in [reg_path,setup_path,terminal_path,fp,manifest_path]},
        global_gateway_prefix_bytes=len(blob),global_gateway_prefix_sha256=hashlib.sha256(blob).hexdigest(),
        supervisor_log_prefix_bytes=len(sb),supervisor_log_prefix_sha256=hashlib.sha256(sb).hexdigest(),supervisor_exit_events=events,
        auditor_source_sha256=sha(__file__),
        scope='Complete1986client/error/output ledger postmortem only. Original collector failure/terminal record retained, not rewritten to pass. Engine disappeared before its end bookend, supervisor recorded exit0, native stderr was not independently captured. No proof of graceful completion, exact native cause, full diagnostic completion, successful-only latency/quality or serving fix.')
    with output.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['requests','successes','errors','status_counts']},indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();audit(a.output)
