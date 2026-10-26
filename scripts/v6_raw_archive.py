"""Lossless post-audit raw archival with verified temporary expansion.

Archives are private raw artifacts. This never runs a serving request or edits
existing evidence. Original files are released only after gzip roundtrip hashes,
complete per-run audit hashes, and the written archive manifest all agree.
"""
import gzip
import hashlib
import json
import shutil
from contextlib import contextmanager
from pathlib import Path


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def uncompressed_sha(path):
    digest=hashlib.sha256()
    with gzip.open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def archive(audit_path,manifest_path):
    audit_path=Path(audit_path);manifest_path=Path(manifest_path)
    audit=json.loads(audit_path.read_text());assert audit['complete'] is True
    expected=audit['raw_sha256'];assert expected and not manifest_path.exists()
    records=[]
    # Validate all originals before writing or releasing any file.
    for name,digest in expected.items():
        path=Path(name);assert path.is_file() and not path.is_symlink() and sha(path)==digest,name
        assert not Path(name+'.gz').exists() and not Path(name+'.gz.partial').exists(),name
    for name,digest in expected.items():
        path=Path(name);dest=Path(name+'.gz');partial=Path(name+'.gz.partial')
        with path.open('rb') as src,partial.open('xb') as out:
            with gzip.GzipFile(filename='',mode='wb',fileobj=out,mtime=0) as gz:shutil.copyfileobj(src,gz)
        assert uncompressed_sha(partial)==digest,name
        partial.rename(dest)
        records.append(dict(path=name,archive=str(dest),sha256=digest,archive_sha256=sha(dest),bytes=path.stat().st_size,archive_bytes=dest.stat().st_size))
    manifest=dict(audit_path=str(audit_path),audit_sha256=sha(audit_path),files=records,
        scope='Lossless private raw archive after complete per-run integrity/quality audit; original uncompressed SHA retained. Not additional benchmark evidence.')
    with manifest_path.open('x') as f:f.write(json.dumps(manifest,indent=2)+'\n')
    # Recheck original identity immediately before unlink. All bytes remain in
    # verified gzip files and can be restored exactly, including newline layout.
    for row in records:
        assert sha(row['path'])==row['sha256'] and uncompressed_sha(row['archive'])==row['sha256']
    for row in records:Path(row['path']).unlink()
    return manifest


@contextmanager
def expanded(manifest_path):
    manifest=json.loads(Path(manifest_path).read_text());created=[]
    assert sha(manifest['audit_path'])==manifest['audit_sha256']
    try:
        for row in manifest['files']:
            path=Path(row['path']);compressed=Path(row['archive'])
            assert sha(compressed)==row['archive_sha256'] and uncompressed_sha(compressed)==row['sha256']
            if path.exists():assert sha(path)==row['sha256']
            else:
                with gzip.open(compressed,'rb') as src,path.open('xb') as dst:shutil.copyfileobj(src,dst)
                assert sha(path)==row['sha256'];created.append(row)
        yield manifest
    finally:
        for row in created:
            assert sha(row['path'])==row['sha256'],'Expanded raw was modified; retain it for inspection'
        for row in created:Path(row['path']).unlink()
