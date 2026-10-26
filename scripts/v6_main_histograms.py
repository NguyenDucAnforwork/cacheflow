"""Passive native metrics outside future matrix request windows; misses stay null."""
import argparse
import hashlib
import json
import time
from datetime import datetime,timezone
from pathlib import Path
import httpx
import psutil
from v6_main_matrix import build_plan
from v5_full_histograms import parse,alive
from v4_services import service_pid


def main():
    p=argparse.ArgumentParser();p.add_argument('pid',type=int);a=p.parse_args();process=psutil.Process(a.pid)
    assert alive(process) and 'scripts/v6_main_matrix.py' in process.cmdline();birth=process.create_time()
    steps=build_plan();base=Path('results/v3');raw=base/'raw'
    existing={s['run_id'] for s in steps if (base/f"{s['run_id']}.setup.json").exists()}
    reg=base/'v6dev1_native_histogram_observer.json';assert not reg.exists()
    reg.write_text(json.dumps(dict(registered_utc=datetime.now(timezone.utc).isoformat(),matrix_pid=a.pid,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        parser_source_sha256=hashlib.sha256(Path('scripts/v5_full_histograms.py').read_bytes()).hexdigest(),
        preexisting_setups_skipped=sorted(existing),
        scope='Two passive metrics GETs per not-yet-started measured arm, outside request window. Any setup already present at registration gets no baseline GET and remains null. No engine reset/parameter/source/profiler change. Exact clock/PID/prompt/generation token deltas and histogram coverage required; native engine-update timing differs from client TPOT proxy.'),indent=2)+'\n')
    print('Registered passive native ITL observer; preexisting misses',len(existing),flush=True)
    for step in steps:
        rid=step['run_id'];marker=base/f'{rid}.setup.json';sp=raw/f'{rid}.summary.json';out=base/f'{rid}.itl_histogram.json'
        assert not out.exists()
        if rid in existing:
            out.write_text(json.dumps(dict(run_id=rid,coverage_valid=False,coverage_failures=['Observer registered after this setup already existed; no retrospective baseline'],before=None,after=None,native_itl_mean_ms=None),indent=2)+'\n');continue
        skipped=False
        while not marker.exists():
            if not alive(process):skipped=True;break
            assert process.create_time()==birth
            outcomes=base/'v6dev1_main_outcomes.json'
            if outcomes.exists():
                try:records=json.loads(outcomes.read_text())['runs']
                except json.JSONDecodeError:records=[]
                if any(r['run_id']==rid+'-warm' and (r['returncode'] or r.get('errors',1)) for r in records):skipped=True;break
            time.sleep(.2)
        if skipped:
            out.write_text(json.dumps(dict(run_id=rid,coverage_valid=False,coverage_failures=['Measured setup absent after failed warmup or terminal matrix'],before=None,after=None,native_itl_mean_ms=None),indent=2)+'\n');continue
        def capture():
            pid=service_pid('cacheflow_v2_vllm');start=time.monotonic_ns()
            try:
                r=httpx.get('http://127.0.0.1:8000/metrics',timeout=5);r.raise_for_status()
                return dict(pid=pid,start_ns=start,end_ns=time.monotonic_ns(),**parse(r.text,'vllm'))
            except Exception as e:return dict(pid=pid,start_ns=start,end_ns=time.monotonic_ns(),error=repr(e))
        before=capture();print('Native histogram baseline',rid,flush=True)
        while not sp.exists():
            assert alive(process),'Matrix ended before current run summary';time.sleep(.2)
        for _ in range(50):
            try:s=json.loads(sp.read_text());break
            except json.JSONDecodeError:time.sleep(.05)
        else:raise RuntimeError('Incomplete terminal summary JSON')
        after=capture();blob=(raw/f'{rid}.jsonl').read_bytes();rows=[json.loads(l) for l in blob.splitlines()];reasons=[]
        if 'error' in before or 'error' in after:reasons.append('Endpoint capture failed')
        if before['pid']!=after['pid'] or before['pid']!=s['engine_pid']:reasons.append('Engine PID mismatch')
        if before['end_ns']>=min(r['scheduled_arrival_ns'] for r in rows):reasons.append('Baseline capture does not precede first scheduled arrival')
        if after['start_ns']<=max(r['complete_ns'] for r in rows):reasons.append('Final capture does not follow response completion')
        bc=before.get('counters',{});ac=after.get('counters',{})
        def delta(name):return ac[name]-bc[name] if name in bc and name in ac else None
        prompt=delta('vllm:prompt_tokens_total');generation=delta('vllm:generation_tokens_total')
        if prompt!=sum(r['input_tokens'] for r in rows):reasons.append('Prompt-token coverage mismatch')
        if any(r['status']!='ok' or r['output_tokens'] is None for r in rows):reasons.append('Incomplete request/generation ledger')
        elif generation!=sum(r['output_tokens'] for r in rows):reasons.append('Generation-token coverage mismatch')
        count=delta('vllm:inter_token_latency_seconds_count');duration=delta('vllm:inter_token_latency_seconds_sum')
        if count is None or count<=0 or duration is None or duration<0:reasons.append('Missing/reset native ITL observations')
        bd=before.get('itl_cumulative_buckets',{});ad=after.get('itl_cumulative_buckets',{})
        histogram={k:ad[k]-bd[k] for k in bd.keys()&ad.keys()}
        if any(v<0 for v in histogram.values()) or histogram.get('+Inf')!=count:reasons.append('Histogram coverage/reset mismatch')
        result=dict(run_id=rid,before=before,after=after,coverage_valid=not reasons,coverage_failures=reasons,
            prompt_tokens_delta=prompt,generation_tokens_delta=generation,itl_observations=count,
            native_itl_mean_ms=duration/count*1000 if not reasons else None,
            native_itl_cumulative_bucket_deltas=histogram if not reasons else None,
            request_file_sha256=hashlib.sha256(blob).hexdigest(),
            limitations='Native engine-output update histogram; buckets give quantile bounds, not exact client per-token ITL. No GPU profiler or per-request token-time join.')
        out.write_text(json.dumps(result,indent=2)+'\n');print('Native histogram coverage',rid,not reasons,reasons,flush=True)


if __name__=='__main__':main()
