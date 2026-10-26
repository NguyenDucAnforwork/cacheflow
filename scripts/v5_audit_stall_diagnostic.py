"""Audit all prospectively registered off/on/off diagnostic outcomes and state."""
import hashlib
import json
from pathlib import Path
from v5_analyze_liveness_probe import summarize


def read(path):return [json.loads(l) for l in path.read_text().splitlines()]


def main():
    base=Path('results/v3');raw=base/'raw';reg_path=base/'v5diag-stall1_registration.json';reg=json.loads(reg_path.read_text())
    for name,digest in reg['source_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    assert hashlib.sha256(Path('/etc/supervisor/conf.d/cacheflow_v2_vllm.conf').read_bytes()).hexdigest()==reg['supervisor_original_sha256']
    actions=reg['actions'];assert len(actions)==15
    rows=[];requests={};engine_pids={};lmcache_pids={}
    for step in actions:
        rid=step['run_id'];s=json.loads((raw/f'{rid}.summary.json').read_text());setup=json.loads((base/f'{rid}.setup.json').read_text())
        rr=read(raw/f'{rid}.jsonl');out={r['request_id']:r for r in read(raw/f'{rid}.outputs.jsonl')}
        assert s['requests']==s['successes']==len(rr)==(60 if step['label']=='warm' else 40) and not s['errors']
        assert s['request_read_timeout_s']==s['request_pool_timeout_s']==180 and s['client_keepalive_connections']==0
        assert setup['gateway_before']['completed_history_requests']==0 and setup['runtime']['cpu_l1_bytes']==16000745472
        assert all(r['status']=='ok' and r['input_tokens']==r['server_prompt_tokens'] and 1<=r['output_tokens']<=96 for r in rr)
        assert len(out)==len(rr) and all(hashlib.sha256(out[r['request_id']]['output'].encode()).hexdigest()==r['output_hash'] for r in rr)
        assert (base/f'{rid}.invalid').exists(),'Every diagnostic must be excluded from performance'
        requests[rid]={r['request_id']:r for r in rr};engine_pids.setdefault(step['phase'],set()).add(s['engine_pid']);lmcache_pids.setdefault(step['phase'],set()).add(s['lmcache_pid'])
        rows.append(dict(**step,requests=s['requests'],errors=0,duration_s=s['duration_s'],engine_pid=s['engine_pid'],
            diagnostic_ttft_p95_ms=s['arrival_ttft_p95_ms'],trace_sha256=s['trace_sha256']))
    assert all(len(p)==1 for p in [*engine_pids.values(),*lmcache_pids.values()])
    assert len(set.union(*engine_pids.values()))==len(set.union(*lmcache_pids.values()))==3
    by={r['run_id']:r for r in rows};pairs=[]
    for label in ['warm','history-fifo','history-bundle','history-union','target']:
        a=f'v5diag-stall1-offA-{label}'
        for phase in ['on','offB']:
            b=f'v5diag-stall1-{phase}-{label}';assert by[a]['trace_sha256']==by[b]['trace_sha256']
            aa,bb=requests[a],requests[b];assert aa.keys()==bb.keys() and all(aa[k]['prompt_sha256']==bb[k]['prompt_sha256'] for k in aa)
            pairs.append(dict(a=a,b=b,output_hash_mismatches=sum(aa[k]['output_hash']!=bb[k]['output_hash'] for k in aa)))
    journals=sorted(raw.glob('v5diag-stall1-probe.*.jsonl'));native=[r for p in journals for r in read(p)]
    analysis=summarize(native);assert analysis['both_native_components_observed'] and not analysis['probe_errors']
    snapshot=max((r for r in native if r['kind']=='scheduler'),key=lambda r:r['duplicate_physical_blocks_above_one_per_expected_hash'])
    count=snapshot['duplicate_physical_blocks_above_one_per_expected_hash'];assert count==920
    assert snapshot['tracked_request_unique_physical_blocks']+snapshot['free_blocks']+1==snapshot['total_blocks']
    nearest=min((r for r in native if r['kind']=='connector_worker'),key=lambda r:abs(r['monotonic_ns']-snapshot['monotonic_ns']))
    result=dict(scope='Complete registered liveness diagnostic, not primary latency/quality evidence. Original prolonged stall did not reproduce across this fixed three-phase experiment; it remains a retained real observation.',
        registration_sha256=hashlib.sha256(reg_path.read_bytes()).hexdigest(),requests=sum(r['requests'] for r in rows),errors=0,
        original_supervisor_config_restored=True,runs=rows,paired_hash_changes=pairs,
        native_journal_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in journals},native_summary=analysis,
        peak_duplicate_snapshot=snapshot,nearby_worker_snapshot=nearest,worker_snapshot_offset_ms=(nearest['monotonic_ns']-snapshot['monotonic_ns'])/1e6,
        duplicate_allocated_kv_payload_bytes=count*16*147456,
        physical_interpretation='Two remote-loading conv44 requests in bundle history each have1776allocated blocks:856shared and920separate each,2696unique physical blocks,33free plus1null in2730block pool.920additional allocations correspond to2.021484375GiB KV payload at144KiB/token. This reconciles allocation metadata only, not successful tensor copies or a causal explanation of the original stall.',
        next='Test a readiness gate with a gate-only FIFO ablation under new prospective method scope; no full research completion or safe-production claim.')
    (base/'v5diag_stall1_complete_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Audited diagnostic',result['requests'],'requests, no errors; duplicate allocated payload',result['duplicate_allocated_kv_payload_bytes'],'bytes; original stall cause remains unproven')


if __name__=='__main__':main()
