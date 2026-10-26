"""Rehearse main warm/measured archive roundtrip on copies of audited real data.

No serving calls; original raw files remain intact. Development evidence only.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from v3_analyze_runs import load
from v6_raw_archive import archive,expanded,sha
from v6_analyze_fairness import analyze as fairness
from v5_analyze_decode import analyze as decode
from v5_analyze_histograms import analyze as histogram
from v5_analyze_waits import analyze as waits
from v6_main_resources import analyze as resources
from v6_native_metrics import summarize

ROOT=Path.cwd()
RID='v6controls1-main-lowload-packing_ready-s101'


def read(path):return json.loads(Path(path).read_text())


def inspect():
    main=load(RID);warm=load(RID+'-warm')
    assert main['summary']['requests']==warm['summary']['requests']==60
    assert main['summary']['engine_pid']==warm['summary']['engine_pid']
    assert main['summary']['lmcache_pid']==warm['summary']['lmcache_pid']
    hp=Path('results/v3')/(RID+'.itl_histogram.json');snap=read(hp)
    native=summarize(RID,snap['before'],snap['after'],list(main['requests'].values()),main['summary'],'vllm')
    assert native['coverage_valid']==snap['coverage_valid'] and native['coverage_failures']==snap['coverage_failures']
    samples=[json.loads(l) for l in Path(f'results/v3/raw/{RID}.metrics.jsonl').read_text().splitlines()]
    return dict(main=main,warm=warm,fairness=fairness(RID),decode=decode(RID),native_itl=histogram(hp),
        waits=waits(dict(runs=[dict(run_id=RID,requests=60)])),resource=resources(samples))


def main():
    ap=ROOT/'results/v3/v6controls1_main_lowload_subset_audit.json'
    qp=ROOT/'results/v3/v6controls1_main_lowload_subset_quality.json'
    audit=read(ap)
    assert audit['subset_complete'] and audit['requests']==540 and audit['errors']==0
    run=next(r for r in audit['runs'] if r['run_id']==RID)
    expected=next(r for r in read(qp)['runs'] if r['run_id']==RID)
    rawfiles=[Path('results/v3/raw')/(rid+suffix) for rid in [RID+'-warm',RID]
        for suffix in ['.jsonl','.outputs.jsonl','.summary.json','.metrics.jsonl','.gateway.jsonl']]
    metadata=[Path('results/v3')/(rid+suffix) for rid in [RID+'-warm',RID]
        for suffix in ['.setup.json','.metrics_summary.json','.itl_histogram.json','.v6_entrypoint.json']]
    metadata.append(Path('results/v3')/(RID+'.host_status.json'))
    hashes={str(p):sha(ROOT/p) for p in [*rawfiles,*metadata]}
    for p in rawfiles:assert audit['artifact_sha256'][str(p)]==hashes[str(p)]
    env=dict(os.environ,PYTHONPATH=str(ROOT/'src'))
    with tempfile.TemporaryDirectory(prefix='cacheflow-main-archive-') as temp:
        temp=Path(temp)
        for source in [*rawfiles,*metadata]:
            target=temp/source;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/source,target)
        os.chdir(temp)
        try:
            before=inspect()
            assert before['fairness']==run['fairness'] and before['decode']==run['secondary'] and before['native_itl']==run['native_itl']
            def grade(output):
                subprocess.run([sys.executable,str(ROOT/'scripts/v2_quality_audit.py'),'--source',str(ROOT/'data/raw/locomo10.json'),
                    '--evaluator',str(ROOT/'data/processed/v2/evaluator/evaluation.py'),'--raw-dir','results/v3/raw',
                    '--run-ids',RID,'--output',output],check=True,env=env)
                return read(output)
            quality_before=grade('before_quality.json');assert quality_before['runs'][0]==expected
            proof=dict(complete=True,requests=60,separate_warmup_requests=60,errors=0,
                raw_sha256={str(p):hashes[str(p)] for p in rawfiles},source_subset_audit_sha256=sha(ap),
                quality_sha256=sha('before_quality.json'),scope='Copied real completed main development arm and warmup; not a full-run audit.')
            Path('copied_audit.json').write_text(json.dumps(proof,indent=2)+'\n')
            manifest=archive('copied_audit.json','archive.json')
            assert len(manifest['files'])==10 and all(not p.exists() for p in rawfiles)
            with expanded('archive.json'):
                assert inspect()==before
                assert grade('after_quality.json')==quality_before
                assert all(sha(p)==hashes[str(p)] for p in rawfiles)
            assert all(not p.exists() for p in rawfiles)
            records=[dict(source_path=r['path'],uncompressed_sha256=r['sha256'],gzip_sha256=r['archive_sha256'],
                uncompressed_bytes=r['bytes'],gzip_bytes=r['archive_bytes']) for r in manifest['files']]
        finally:os.chdir(ROOT)
    assert all(sha(ROOT/p)==h for p,h in hashes.items())
    sources=['scripts/v6_rehearse_main_archival.py','scripts/v6_raw_archive.py','scripts/v3_analyze_runs.py',
        'scripts/v6_analyze_fairness.py','scripts/v3_audit_admission.py','scripts/v5_analyze_decode.py',
        'scripts/v5_analyze_histograms.py','scripts/v5_analyze_waits.py','scripts/v6_main_resources.py',
        'scripts/v6_native_metrics.py','scripts/v2_quality_audit.py']
    result=dict(rehearsal_passed=True,source_run_id=RID,existing_measured_requests=60,existing_warmup_requests=60,
        new_inference_requests=0,serving_calls=0,source_subset_audit_sha256=sha(ap),source_quality_sha256=sha(qp),
        original_artifact_sha256=hashes,copied_archive=records,byte_roundtrip_equal=True,
        measured_and_warm_integrity_equal=True,official_quality_json_equal=True,fairness_equal=True,
        completion_decode_equal=True,native_histogram_equal=True,additive_waits_equal=True,sampled_resources_equal=True,
        original_artifacts_unchanged=True,evaluator_sha256=quality_before['evaluator_sha256'],
        answerable_f1=expected['answerable_f1'],analysis_source_sha256={n:sha(n) for n in sources},
        scope='Temporary copies of one real audited 60-QA main development arm plus60warmup. Ten raw files include both gateway logs. Full official quality and integrity/fairness/decode/histogram/waits/resources match before/after archival. No serving calls, original raw deletion, full1986QA/48GB validation, new performance result or liveness proof.')
    output=ROOT/'results/v3/v6_main_archival_rehearsal.json';output.write_text(json.dumps(result,indent=2)+'\n')
    print('Main archival rehearsal passes:10raw files,60measured+60warm,0new inference; originals unchanged',flush=True)


if __name__=='__main__':main()
