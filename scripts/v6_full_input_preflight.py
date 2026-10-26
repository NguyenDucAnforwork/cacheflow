"""Before full GPU execution, compare every token ID across the pinned environments."""
import argparse
import gzip
import hashlib
import json
import os
import subprocess
from datetime import datetime,timezone
from pathlib import Path
from v4_services import service_pid
from v6_trace_hashes import CanonicalTraceDigest

TRACES=[Path(f'data/processed/v3/v5-full4b-qps4-s{s}.jsonl.gz') for s in [901,902,903]]


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def compare(main,native,expected=1986):
    assert main['cpu_only'] and native['cpu_only'] and main['complete_trace'] and native['complete_trace']
    assert main['model_revision']==native['model_revision']
    for field in ['trace_stored_sha256','trace_uncompressed_sha256','trace_canonical_sha256']:assert main[field]==native[field]
    assert main['tokenizer_artifact_sha256']==native['tokenizer_artifact_sha256']
    def keyed(data):
        rr=data['requests'];by={(r['sample_id'],r['qa_index']):r for r in rr}
        assert len(by)==len(rr)==expected
        return by
    a=keyed(main);b=keyed(native);assert a.keys()==b.keys()
    for key in a:
        for field in ['input_tokens','max_tokens','prompt_sha256','token_ids_u32le_sha256']:assert a[key][field]==b[key][field],(key,field)
    assert main['page16']==native['page16'] and main['page16']['requests']==expected
    assert main['page16']['input_tokens']==sum(r['input_tokens'] for r in a.values())
    return a



def non_arrival_identity(row):
    content=dict(row);content.pop('offset_ms')
    return hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');a=p.parse_args()
    commands=[[python,'scripts/v6_token_fingerprints.py','--backend',backend,'--trace',str(TRACES[0]),'--output',backend+'.json']
        for backend,python in [('main','/venv/main/bin/python'),('native','/venv/sglang-baseline/bin/python')]]
    if a.plan:print(json.dumps(dict(cpu_only=True,requests=1986,commands=commands,verify_semantic_traces=list(map(str,TRACES))),indent=2));return
    for name in ['cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache','cacheflow_v3_sglang']:assert service_pid(name)==0,'Full CPU input preflight requires idle serving services'
    final=Path('results/v3/v6full1_input_preflight.json');assert not final.exists()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+str(os.getpid());attempt=Path('results/v3/input_preflight')/stamp;attempt.mkdir(parents=True)
    registration=dict(started_utc=datetime.now(timezone.utc).isoformat(),cpu_only=True,source_sha256=sha(__file__),worker_sha256=sha('scripts/v6_token_fingerprints.py'),trace_sha256={str(t):sha(t) for t in TRACES})
    (attempt/'registration.json').write_text(json.dumps(registration,indent=2)+'\n')
    env=dict(os.environ,PYTHONPATH='src',LD_LIBRARY_PATH='/venv/main/lib/python3.12/site-packages/nvidia/cu13/lib:'+os.environ.get('LD_LIBRARY_PATH',''))
    for command in commands:
        command[-1]=str(attempt/command[-1]);subprocess.run(command,check=True,env=env)
    mp=attempt/'main.json';np=attempt/'native.json';m=json.loads(mp.read_text());n=json.loads(np.read_text());reference=compare(m,n)
    semantic={k:(r['prompt_sha256'],r['input_tokens'],r['max_tokens']) for k,r in reference.items()};inputs={};reference_identity=None
    for trace in TRACES:
        digest=hashlib.sha256();canonical=CanonicalTraceDigest();actual={};identities={}
        with gzip.open(trace,'rb') as f:
            for line in f:
                digest.update(line);r=json.loads(line);canonical.update(r);key=(r['sample_id'],r['qa_index']);assert key not in actual
                actual[key]=(hashlib.sha256(r['prompt'].encode()).hexdigest(),r['input_tokens'],r['max_tokens']);identities[key]=non_arrival_identity(r)
        if reference_identity is None:reference_identity=identities
        else:assert identities==reference_identity,'Nonarrival trace metadata changed across seeds'
        manifest=json.loads(trace.with_suffix('.manifest.json').read_text());assert actual==semantic and canonical.hexdigest()==manifest['trace_sha256']
        assert manifest['requests']==1986 and manifest['prompt_version']=='locomo-qwen-concise-v5' and manifest['abstention_style']=='official_consistent_system_and_user'
        inputs[str(trace)]=dict(stored_sha256=sha(trace),uncompressed_sha256=digest.hexdigest(),canonical_sha256=canonical.hexdigest(),nonarrival_identity_sha256=hashlib.sha256(json.dumps(sorted(identities.items()),separators=(',',':')).encode()).hexdigest(),manifest_sha256=sha(trace.with_suffix('.manifest.json')))
    result=dict(complete=True,cpu_only=True,requests=1986,token_id_mismatches=0,semantic_trace_mismatches=0,inputs=inputs,
        main_fingerprints_path=str(mp),native_fingerprints_path=str(np),main_fingerprints_sha256=sha(mp),native_fingerprints_sha256=sha(np),
        registration_path=str(attempt/'registration.json'),registration_sha256=sha(attempt/'registration.json'),
        worker_sha256=sha('scripts/v6_token_fingerprints.py'),source_sha256=sha(__file__),page16=m['page16'],
        scope='All1986input token vectors match main/native loaders; same QA/prompt/output budgets across3arrival traces. CPU-only provenance check, not model serving, actual KV contents, full benchmark quality/performance or production liveness.')
    with final.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print('Full CPU input preflight passed1986prompts across both environments and3arrival traces',flush=True)


if __name__=='__main__':main()
