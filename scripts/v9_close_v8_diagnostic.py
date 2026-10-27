"""Reopen V8 offA/on/offB evidence across explicit amendment lineage."""
import json
from pathlib import Path
from v6_raw_archive import sha
from v6_main_resources import analyze
from v7_observe_full_liveness import parsed_lines
from v8_analyze_liveness import windows,describe_window


def main():
    base=Path('results/v3');out=base/'v8_bracketed_diagnostic_closure.json';assert not out.exists()
    terminal_path=base/'v8diag3_terminal.json';terminal=json.loads(terminal_path.read_text())
    assert terminal['diagnostic_execution_complete'] and terminal['cleanup_errors']==[] and terminal['error'] is None and len(terminal['outcomes'])==4
    rows=[];engines=set();caches=set()
    for phase,rid in [('offA','v8diag1-offA-target'),('on','v8diag3-on-target'),('offB','v8diag3-offB-target')]:
        raw=base/'raw';summary_path=raw/(rid+'.summary.json');s=json.loads(summary_path.read_text());setup_path=base/(rid+'.diagnostic_setup.json');setup=json.loads(setup_path.read_text())
        if phase=='offA':
            proof_path=base/'v8diag1_offA_postmortem_integrity.json';proof=json.loads(proof_path.read_text())
            assert proof['kind']=='postmortem_client_record_integrity_after_collector_failure'
        else:
            proof_path=base/(rid+'.diagnostic_integrity.json');proof=json.loads(proof_path.read_text());assert proof['diagnostic_integrity_checked'] and not proof['performance_valid']
            outcome=next(r for r in terminal['outcomes'] if r['run_id']==rid);assert outcome==proof
        for name,digest in proof['raw_sha256'].items():assert sha(name)==digest,name
        assert proof['requests']==s['requests']==1986 and proof['successes']==s['successes'] and proof['errors']==s['errors']
        assert setup['step']['probe']==(phase=='on') and setup['step']['policy']=='packing_reuse' and setup['runtime']['cpu_l1_bytes']==48002236416
        assert s['request_read_timeout_s']==s['request_pool_timeout_s']==600 and s['client_keepalive_connections']==0
        engine=(setup['engine']['pid'],setup['engine']['birth']);cache=(setup['lmcache']['pid'],setup['lmcache']['birth'])
        assert engine not in engines and cache not in caches;engines.add(engine);caches.add(cache)
        samples=parsed_lines((raw/(rid+'.metrics.jsonl')).read_bytes());longest,_=windows(samples)
        resource=analyze(samples);source=resource['strict_counter_deltas']['vllm']
        if s['errors']==0:
            assert source['vllm:prompt_tokens_total']==50522325
            assert source['vllm:prompt_tokens_cached_total']+source['vllm:request_prefill_kv_computed_tokens_sum']==50522325
        warm=raw/(rid.replace('-target','-warm')+'.summary.json');w=json.loads(warm.read_text());assert w['requests']==w['successes']==60 and w['errors']==0 and w['engine_pid']==s['engine_pid']
        rows.append(dict(phase=phase,run_id=rid,requests=1986,successes=s['successes'],errors=s['errors'],probe_enabled=phase=='on',
            summary_sha256=sha(summary_path),setup_sha256=sha(setup_path),integrity_sha256=sha(proof_path),
            longest_sampled_nonprogress=describe_window(longest),source_counters=source,
            scope='Whole client cohort; failed source deltas may be null. No latency/quality/speedup contrast.'))
    result=dict(diagnostic_attempts_reopened=True,original_v8diag1_complete=False,amended_v8diag3_complete=True,performance_valid=False,research_complete=False,
        terminal_sha256=sha(terminal_path),observer_source_sha256=sha(__file__),target_requests=5958,separate_warmups=180,distinct_engines=3,distinct_cpu_caches=3,phases=rows,
        scope='Cross-namespace offA/on/offB chronology explicitly retains offA collector/engine failure and diag2 preflight failure. On/offB complete, offAfailed; no deterministic probe-cause, deadlock fix, hidden retry, quality equivalence, DMA or primary performance result. Original V6full still10complete/1failed/19unexecuted. Native intervention requires its own registered evidence.')
    out.write_text(json.dumps(result,indent=2)+'\n');print('Reopened V8 chronology:',[(r['phase'],r['successes'],r['errors']) for r in rows],flush=True)


if __name__=='__main__':main()
