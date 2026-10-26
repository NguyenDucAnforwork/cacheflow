"""Complete per-run audit/official quality before any raw archival."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from v6_freeze_full import verify_full,PATH,sha
from v6_full_contracts import audit_configuration
from v6_native_metrics import summarize
from v5_analyze_histograms import analyze as histogram
from v5_analyze_decode import analyze as decode
from v6_analyze_fairness import analyze as fairness
from v3_analyze_runs import load
from v4_audit_sglang_runs import audit as native_integrity
from v6_native_resources import analyze as native_resources
from v6_main_resources import analyze as main_resources
from v5_analyze_waits import analyze as waits


def read(path):return json.loads(Path(path).read_text())


def main():
    p=argparse.ArgumentParser();p.add_argument('run_id');a=p.parse_args();parent,seal,freeze=verify_full()
    step=next(s for s in freeze['actions'] if s['run_id']==a.run_id);rid=step['run_id'];sg=step['engine']=='sg'
    base=Path('results/v3/sglang' if sg else 'results/v3');raw=Path('results/v3/raw/sglang' if sg else 'results/v3/raw')
    auditpath=Path('results/v3')/(rid+'.full_audit.json');assert not auditpath.exists()
    rawfiles=[];summaries=[]
    for warm in [True,False]:
        current=rid+'-warm' if warm else rid;summary=read(raw/(current+'.summary.json'));setup=read(base/(current+'.setup.json'))
        assert not (base/(current+'.invalid')).exists()
        m=read(Path('data/processed/v3/v5-dev4b3-qps4-s101.jsonl' if warm else step['trace']).with_suffix('.manifest.json'))
        assert summary['trace_sha256']==m['trace_sha256'] and m['renderer_sha256']==seal['source_sha256']['src/cacheflow/v5_prompt.py']
        assert m['abstention_style']=='official_consistent_system_and_user'
        rows=[json.loads(l) for l in (raw/(current+'.jsonl')).read_text().splitlines()]
        outputs=[json.loads(l) for l in (raw/(current+'.outputs.jsonl')).read_text().splitlines()]
        by={r['request_id']:r for r in rows};texts={r['request_id']:r for r in outputs}
        assert len(by)==len(rows)==len(outputs)==len(texts)==summary['requests'] and by.keys()==texts.keys()
        import hashlib
        assert all(r['status']=='ok' and r['server_prompt_tokens']==r['input_tokens'] and 0<r['output_tokens']<=96 and r['run_id']==current for r in rows)
        assert all(hashlib.sha256(texts[k]['output'].encode()).hexdigest()==by[k]['output_hash'] for k in by)
        entry=None if sg else read(base/(current+'.v6_entrypoint.json'))
        audit_configuration(dict(step,run_id=current),setup,summary,entry,parent,seal,freeze,warm)
        if sg:
            counters=read(base/(current+'.metrics_summary.json'))['counter_deltas']
            assert counters['sglang:prompt_tokens_total']==sum(r['input_tokens'] for r in rows)
            if not warm:native_integrity(current)
        else:load(current)
        summaries.append(summary)
        for suffix in ['.jsonl','.outputs.jsonl','.summary.json','.metrics.jsonl']:
            rawfiles.append(raw/(current+suffix))
        if not sg or setup['gateway_policy']:rawfiles.append(raw/(current+'.gateway.jsonl'))
    assert summaries[0]['engine_pid']==summaries[1]['engine_pid']
    if not sg:assert summaries[0]['lmcache_pid']==summaries[1]['lmcache_pid']
    summary=summaries[1];setup=read(base/(rid+'.setup.json'));data=(raw/(rid+'.jsonl')).read_bytes();rows=[json.loads(l) for l in data.splitlines()]
    snapshotpath=base/(rid+'.itl_histogram.json');snapshot=read(snapshotpath)
    assert snapshot['request_file_sha256']==sha(raw/(rid+'.jsonl'))
    verified=summarize(rid,snapshot['before'],snapshot['after'],rows,summary,'sglang' if sg else 'vllm')
    assert verified['coverage_valid']==snapshot['coverage_valid'] and verified['coverage_failures']==snapshot['coverage_failures']
    qualitypath=Path('results/v3')/(rid+'.full_quality.json')
    subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir',str(raw),'--run-ids',rid,'--output',str(qualitypath)],check=True)
    quality=read(qualitypath)['runs'][0];assert quality['answerable_n']==1540 and quality['by_category']['5']['n']==446
    metrics=read(base/(rid+'.metrics_summary.json'));host={};resource=None
    if not sg:
        actual=read(base/(rid+'.host_status.json'))['storage_manager']['l1_manager']['memory_total_bytes']
        assert actual==freeze['expected_main_heap_bytes'];host=dict(actual_main_heap_bytes=actual,configured_payload_bytes=freeze['host_payload_bytes'])
        samples=[json.loads(l) for l in (raw/(rid+'.metrics.jsonl')).read_text().splitlines()]
        resource=main_resources(samples)
        for key in ['vllm:prompt_tokens_total','vllm:prompt_tokens_cached_total','vllm:request_prefill_kv_computed_tokens_sum','vllm:prompt_tokens_source_external_kv_transfer_total']:
            assert resource['strict_counter_deltas']['vllm'][key]==metrics['counter_deltas']['vllm'][key] and resource['strict_counter_deltas']['vllm'][key] is not None,key
    else:
        samples=[json.loads(l) for l in (raw/(rid+'.metrics.jsonl')).read_text().splitlines()]
        resource=native_resources(samples);observed=resource['host_capacity_tokens'];assert observed is not None
        assert observed*147456==freeze['expected_native_host_bytes']
        host=dict(observed_native_host_capacity_tokens=observed,observed_native_host_payload_bytes=observed*147456)
    result=dict(complete=True,run_id=rid,step=step,freeze_sha256=sha(PATH),requests=1986,errors=0,
        separate_warmup_requests=60,engine_pid=summary['engine_pid'],lmcache_pid=summary.get('lmcache_pid'),
        summary=summary,quality_sha256=sha(qualitypath),quality=quality,
        setup_sha256=sha(base/(rid+'.setup.json')),warm_setup_sha256=sha(base/(rid+'-warm.setup.json')),
        host=host,metrics=metrics,resource=resource,native_itl=histogram(snapshotpath),secondary=decode(rid),fairness=fairness(rid),waits=waits(dict(runs=[dict(run_id=rid,requests=1986)])),
        raw_sha256={str(p):sha(p) for p in rawfiles},
        scope='Complete measured full-run integrity+official quality and separate warmup integrity. No SOTA/quality-equivalence/liveness proof. Raw remains private and may be losslessly archived after this audit; every original byte SHA retained.')
    auditpath.write_text(json.dumps(result,indent=2)+'\n');print('Full arm audited',rid,flush=True)


if __name__=='__main__':main()
