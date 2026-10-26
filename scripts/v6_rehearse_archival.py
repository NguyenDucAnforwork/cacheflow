"""Exercise audit/quality/archive/expand on copies of a real completed native run.

No serving calls, new inference, original-result mutation, or full-study claim.
Temporary copies are removed; the original raw artifacts remain unchanged.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from v4_audit_sglang_runs import audit as integrity
from v6_raw_archive import archive,expanded

ROOT=Path.cwd();RID='v6native1-primary-s101-native'


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    native=ROOT/'results/v3/sglang';raw=ROOT/'results/v3/raw/sglang';sourceaudit=native/'v6native1_audit.json'
    a=json.loads(sourceaudit.read_text());assert a['complete'] and a['requests']==2700 and not a['errors']
    assert any(r['run_id']==RID and r['requests']==60 for r in a['runs'])
    sources=[raw/(RID+s) for s in ['.jsonl','.outputs.jsonl','.summary.json','.metrics.jsonl']]
    source_hashes={str(p.relative_to(ROOT)):sha(p) for p in sources}
    expected=next(r for r in json.loads((native/'v6native1_quality.json').read_text())['runs'] if r['run_id']==RID)
    env=dict(os.environ,PYTHONPATH=str(ROOT/'src'))
    with tempfile.TemporaryDirectory(prefix='cacheflow-archival-') as temp:
        temp=Path(temp)
        for source in [*sources,native/(RID+'.setup.json'),native/(RID+'.metrics_summary.json')]:
            target=temp/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        os.chdir(temp)
        try:
            first=integrity(RID);assert first['requests']==60 and first['errors']==0
            def grade(output):
                subprocess.run([sys.executable,str(ROOT/'scripts/v2_quality_audit.py'),'--source',str(ROOT/'data/raw/locomo10.json'),
                    '--evaluator',str(ROOT/'data/processed/v2/evaluator/evaluation.py'),'--raw-dir','results/v3/raw/sglang','--run-ids',RID,'--output',output],check=True,env=env)
                return json.loads(Path(output).read_text())
            quality_before=grade('quality_before.json');assert quality_before['runs'][0]==expected
            copied_audit=dict(complete=True,requests=60,errors=0,source_complete_audit_sha256=sha(sourceaudit),quality_sha256=sha('quality_before.json'),
                raw_sha256=source_hashes,scope='Temporary-copy rehearsal of one real completed native development arm, not full1986QA or a new inference run.')
            Path('audit.json').write_text(json.dumps(copied_audit,indent=2)+'\n')
            manifest=archive('audit.json','archive.json');assert all(not Path(p).exists() for p in source_hashes)
            with expanded('archive.json'):
                assert integrity(RID)==first
                quality_after=grade('quality_after.json');assert quality_after==quality_before
                assert all(sha(p)==digest for p,digest in source_hashes.items())
            assert all(not Path(p).exists() for p in source_hashes)
            records=[dict(source_path=r['path'],uncompressed_sha256=r['sha256'],gzip_sha256=r['archive_sha256'],uncompressed_bytes=r['bytes'],gzip_bytes=r['archive_bytes']) for r in manifest['files']]
            result=dict(rehearsal_passed=True,serving_calls=0,new_inference_requests=0,source_run_id=RID,existing_requests=60,
                source_native_audit_sha256=sha(sourceaudit),source_quality_sha256=sha(native/'v6native1_quality.json'),source_raw_sha256=source_hashes,
                copied_raw_archive=records,byte_roundtrip_equal=True,integrity_equal_after_expansion=True,official_quality_equal_after_expansion=True,
                answerable_f1=expected['answerable_f1'],by_category=expected['by_category'],evaluator_sha256=quality_before['evaluator_sha256'],
                rehearsal_source_sha256=sha(ROOT/'scripts/v6_rehearse_archival.py'),archive_implementation_sha256=sha(ROOT/'scripts/v6_raw_archive.py'),
                scope='Real60QA development outputs on temporary byte-identical copies. Official evaluator/integrity pass before and after lossless archive/expand. No original raw deletion, model serving, full1986QA,48GBGPU validation or production-liveness evidence.')
        finally:os.chdir(ROOT)
    assert all(sha(ROOT/p)==digest for p,digest in source_hashes.items())
    result['original_raw_unchanged']=True
    (ROOT/'results/v3/v6_archival_rehearsal.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Real60QA archival rehearsal passes; original raw unchanged,0new serving requests',flush=True)


if __name__=='__main__':main()
