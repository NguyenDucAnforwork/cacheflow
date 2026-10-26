"""From-source full input reproduction, queued behind a verified serving job.

Never loads frozen trace prompts as generation input. Generation uses official
LoCoMo, the pinned renderer/tokenizer and published workload parameters. Byte
hashes of the sealed inputs are acceptance targets, including gzip metadata.
"""
import argparse
import gzip
import hashlib
import importlib.metadata
import json
import random
import shutil
import struct
import sys
import time
from collections import Counter
from dataclasses import asdict,replace
from datetime import datetime,timezone
from pathlib import Path
import psutil
from cacheflow.locomo import V2TraceRow,load_locomo
from cacheflow.v5_prompt import render
from v6_raw_archive import sha
from v6_trace_hashes import CanonicalTraceDigest,scan
from v6_trace_storage import restore_copy

FREEZE=Path('results/v3/v6full1_freeze.json')
RECIPE=Path('results/v3/v6full1_gzip_metadata.json')
SERVICES=['cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache','cacheflow_v3_sglang']


def source_rows(conversations,tokenizer,samples,*,output_tokens=96,max_model_len=32768):
    selected=[c for c in conversations if c.sample_id in samples]
    assert [c.sample_id for c in selected]==list(samples),'Source conversation order differs'
    rows=[];fingerprints=[]
    for index in range(max(len(c.questions) for c in selected)):
        for c in selected:
            if index>=len(c.questions):continue
            q=c.questions[index];text=render(tokenizer,c,q);ids=tokenizer.encode(text,add_special_tokens=False)
            assert len(ids)+output_tokens<=max_model_len
            row=V2TraceRow(request_id=f'{c.sample_id}-q{q.index:03d}',offset_ms=0,prompt=text,input_tokens=len(ids),max_tokens=output_tokens,
                group=c.sample_id,sample_id=c.sample_id,qa_index=q.index,category=q.category,protocol='p_qa',checkpoint_session=None)
            rows.append(row)
            fingerprints.append(dict(request_id=row.request_id,sample_id=row.sample_id,qa_index=row.qa_index,input_tokens=len(ids),max_tokens=row.max_tokens,
                prompt_sha256=hashlib.sha256(text.encode()).hexdigest(),token_ids_u32le_sha256=hashlib.sha256(struct.pack('<'+'I'*len(ids),*ids)).hexdigest()))
    return rows,fingerprints


def write_schedule(rows,path,seed,qps):
    assert not Path(path).exists() and qps>0
    rng=random.Random(seed);now=0;canonical=CanonicalTraceDigest()
    with gzip.open(path,'wt',encoding='utf-8') as output:
        for row in rows:
            now+=rng.expovariate(qps)*1000;item=asdict(replace(row,offset_ms=round(now)))
            output.write(json.dumps(item,sort_keys=True)+'\n');canonical.update(item)
    return canonical.hexdigest()


def idle():
    from v4_services import service_pid
    assert all(service_pid(name)==0 for name in SERVICES),'Serving must be idle before full regeneration'


def register(pid,path):
    path=Path(path);assert not path.exists()
    process=psutil.Process(pid)
    assert process.is_running() and process.status()!=psutil.STATUS_ZOMBIE
    assert 'scripts/v6_continue_full_r1.py' in process.cmdline(),'Unexpected dependent job'
    freeze=json.loads(FREEZE.read_text());recipe=json.loads(RECIPE.read_text())
    assert recipe['reference_freeze_sha256']==sha(FREEZE)
    preflight_path=Path(recipe['reference_preflight_path']);preflight=json.loads(preflight_path.read_text())
    fingerprints=Path(preflight['main_fingerprints_path'])
    sources=[__file__,'src/cacheflow/locomo.py','src/cacheflow/v5_prompt.py','scripts/v6_raw_archive.py','scripts/v6_trace_hashes.py','scripts/v6_trace_storage.py','scripts/v4_services.py','scripts/v3_model.py']
    metadata=[FREEZE,RECIPE,preflight_path,fingerprints,Path('results/v3/v6full1_continuation_r1_registration.json')]
    metadata += [Path(s['trace']).with_suffix('.manifest.json') for s in freeze['actions']]
    metadata=list(dict.fromkeys(map(str,metadata)))
    assert sha(preflight_path)==recipe['reference_preflight_sha256'] and sha(fingerprints)==preflight['main_fingerprints_sha256']
    source='data/raw/locomo10.json';assert sha(source)==freeze['source_data_sha256']
    model={n:d for n,d in freeze['model_artifact_sha256'].items() if not n.endswith('.safetensors')}
    r=dict(kind='cpu_only_from_official_source_full_input_regeneration',registered_utc=datetime.now(timezone.utc).isoformat(),
        after_pid=pid,after_create_time=process.create_time(),after_argv=process.cmdline(),source_sha256={str(n):sha(n) for n in sources},
        reference_metadata_sha256={n:sha(n) for n in metadata},official_source_path=source,official_source_sha256=sha(source),tokenizer_artifact_sha256=model,
        package_versions=freeze['main_package_versions'],
        scope='Queued CPU-only verification after the exact live controller terminates and all serving services are idle. No model weights, GPU calls, original input writes, serving retries or full-study completion claim. Preparation/unit tests are not a completed1986QAregeneration result.')
    with path.open('x') as output:output.write(json.dumps(r,indent=2)+'\n')
    return r


def wait_parent(r):
    while True:
        try:
            process=psutil.Process(r['after_pid'])
            # A different birth time proves the registered process has ended.
            # Never wait on or interfere with its unrelated PID replacement.
            if process.create_time()!=r['after_create_time']:return
            if not process.is_running() or process.status()==psutil.STATUS_ZOMBIE:return
            assert process.cmdline()==r['after_argv'],'Registered process changed command line'
        except psutil.NoSuchProcess:return
        time.sleep(5)


def execute(registration):
    registration=Path(registration);r=json.loads(registration.read_text());assert r['kind']=='cpu_only_from_official_source_full_input_regeneration'
    result_path=registration.with_suffix('.result.json');assert not result_path.exists() and not registration.with_suffix('.failure.json').exists(),'Retain prior terminal attempt; no implicit retry'
    print('Waiting on verified controller',r['after_pid'],r['after_create_time'],flush=True)
    wait_parent(r);idle()
    for group in ['source_sha256','reference_metadata_sha256','tokenizer_artifact_sha256']:
        for name,digest in r[group].items():assert sha(name)==digest,(group,name)
    assert sha(r['official_source_path'])==r['official_source_sha256']
    assert all(importlib.metadata.version(name)==v for name,v in r['package_versions'].items())
    freeze=json.loads(FREEZE.read_text());recipe=json.loads(RECIPE.read_text());paths=sorted({s['trace'] for s in freeze['actions']})
    assert len(paths)==3
    minimum=2*max(Path(p).stat().st_size for p in paths)+64*1024**2
    assert shutil.disk_usage('.').free>=minimum,'Insufficient space for one generated and restored gzip copy'
    preflight=json.loads(Path(recipe['reference_preflight_path']).read_text());reference=json.loads(Path(preflight['main_fingerprints_path']).read_text())
    manifests={p:json.loads(Path(p).with_suffix('.manifest.json').read_text()) for p in paths}
    assert {m['seed'] for m in manifests.values()}=={901,902,903}
    base=manifests[paths[0]]
    for m in manifests.values():
        assert m['protocol']=='p_qa' and m['arrival']=='interleaved' and m['requests']==1986 and m['qps']==4
        for key in ['selected_samples','max_model_len','output_tokens','model_revision','excluded']:
            assert m[key]==base[key],key
        assert m['excluded']==dict(no_evidence=0,context_too_long=0)
    # Heavy tokenizer imports/work happen only after the idle gate above.
    from transformers import AutoTokenizer
    from v3_model import get_model
    model=get_model('qwen3-4b');assert model['revision']==freeze['model_revision']
    tokenizer=AutoTokenizer.from_pretrained(model['path'],local_files_only=True)
    rows,fingerprints=source_rows(load_locomo(r['official_source_path']),tokenizer,base['selected_samples'],
        output_tokens=base['output_tokens'],max_model_len=base['max_model_len'])
    assert len(rows)==1986 and fingerprints==reference['requests'],'Regenerated prompt/token identity differs'
    counts=Counter(row.category for row in rows);assert counts[5]==446 and len(rows)-counts[5]==1540
    attempt=registration.parent/(registration.stem+'_copies');attempt.mkdir();proofs=[]
    for name in paths:
        idle();assert sha(name)==freeze['input_file_sha256'][name]==recipe['traces'][name]['stored_sha256']
        generated=attempt/Path(name).name;restored=attempt/('restored-'+Path(name).name)
        canonical=write_schedule(rows,generated,manifests[name]['seed'],manifests[name]['qps'])
        assert canonical==preflight['inputs'][name]['canonical_sha256']
        identity=scan(generated);assert identity['requests']==1986 and identity['uncompressed_sha256']==preflight['inputs'][name]['uncompressed_sha256']
        restored_proof=restore_copy(generated,restored,recipe['traces'][name]);assert sha(restored)==sha(name)
        proof=dict(original_path=name,seed=manifests[name]['seed'],generated_identity=identity,restored_identity=restored_proof,
            original_stored_sha256=sha(name),requests=1986,canonical_sha256=canonical,generated_from_official_source=True,
            temporary_copies_removed_after_verified_identity=True)
        with (attempt/(str(proof['seed'])+'.proof.json')).open('x') as output:output.write(json.dumps(proof,indent=2)+'\n')
        # Only our new, hash-verified duplicates are released. The serving inputs
        # are never opened for writing, renamed or removed.
        assert sha(generated)==identity['stored_sha256'] and sha(restored)==proof['original_stored_sha256']
        generated.unlink();restored.unlink();proofs.append(proof)
        print('Verified from-source1986QAseed',proof['seed'],flush=True)
    assert all(sha(name)==freeze['input_file_sha256'][name] for name in paths)
    result=dict(complete=True,cpu_only=True,registration_sha256=sha(registration),finished_utc=datetime.now(timezone.utc).isoformat(),
        unique_qa=1986,answerable=1540,category5=446,input_tokens=sum(row.input_tokens for row in rows),
        prompt_and_token_fingerprints_equal=True,original_inputs_unchanged=True,seeds=proofs,
        scope='All1986prompts/token vectors rebuilt from official LoCoMo and pinned tokenizer/renderer; all3scheduled gzip files match sealed plain/canonical/stored hashes after captured header restoration. No model weights, inference, performance reproduction, quality evaluation or complete research claim.')
    with result_path.open('x') as output:output.write(json.dumps(result,indent=2)+'\n')
    print('Full input regeneration verified',str(result_path),flush=True)


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('register');a.add_argument('pid',type=int);a.add_argument('output',type=Path)
    a=sub.add_parser('execute');a.add_argument('registration',type=Path)
    a=p.parse_args()
    if a.command=='register':register(a.pid,a.output);print('Registered input reproduction waiter',a.output,flush=True)
    else:
        try:execute(a.registration)
        except Exception as exc:
            failure=a.registration.with_suffix('.failure.json')
            with failure.open('x') as output:output.write(json.dumps(dict(complete=False,error=repr(exc),scope='Preserved input-reproduction failure; no serving/input changes or automatic retries'),indent=2)+'\n')
            raise


if __name__=='__main__':main()
