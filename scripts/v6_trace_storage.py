"""Preserve gzip metadata for byte-exact regeneration; never overwrite inputs.

Restore copies the regenerated DEFLATE stream unchanged, replacing only its
header. Publication requires the original sealed file SHA and plain-byte SHA.
"""
import argparse
import json
import os
import platform
import shutil
import struct
import zlib
from pathlib import Path
from v6_raw_archive import sha,uncompressed_sha


def header(stream):
    start=stream.tell();fixed=stream.read(10)
    assert len(fixed)==10 and fixed[:3]==b'\x1f\x8b\x08' and not fixed[3]&0xe0,'Unsupported gzip header'
    flags=fixed[3]
    if flags&4:
        size=stream.read(2);assert len(size)==2
        extra=stream.read(struct.unpack('<H',size)[0]);assert len(extra)==struct.unpack('<H',size)[0]
    for flag in [8,16]:
        if flags&flag:
            while True:
                char=stream.read(1);assert char and stream.tell()-start<1024**2,'Truncated/oversized gzip header'
                if char==b'\0':break
    if flags&2:assert len(stream.read(2))==2
    end=stream.tell();stream.seek(start);result=stream.read(end-start);assert len(result)==end-start
    return result


def reference(freeze_path):
    freeze_path=Path(freeze_path);freeze=json.loads(freeze_path.read_text())
    assert freeze['status']=='frozen_prospective_full_study_not_completion'
    paths=[p for p in freeze['preflight_artifact_sha256'] if p.endswith('_input_preflight.json')];assert len(paths)==1
    preflight=Path(paths[0]);assert sha(preflight)==freeze['preflight_artifact_sha256'][str(preflight)]
    proof=json.loads(preflight.read_text());assert proof['complete'] and proof['requests']==1986 and proof['cpu_only']
    return freeze,proof,preflight


def record(freeze_path,output):
    freeze_path=Path(freeze_path);output=Path(output);assert not output.exists()
    freeze,proof,preflight=reference(freeze_path);traces={}
    for name in sorted({s['trace'] for s in freeze['actions']}):
        path=Path(name);assert path.suffix=='.gz'
        expected=freeze['input_file_sha256'][name];assert sha(path)==expected==proof['inputs'][name]['stored_sha256']
        with path.open('rb') as stream:raw=header(stream)
        traces[name]=dict(header_hex=raw.hex(),header_bytes=len(raw),mtime=struct.unpack('<I',raw[4:8])[0],
            stored_sha256=expected,uncompressed_sha256=proof['inputs'][name]['uncompressed_sha256'],
            canonical_sha256=proof['inputs'][name]['canonical_sha256'])
    result=dict(reference_freeze_path=str(freeze_path),reference_freeze_sha256=sha(freeze_path),
        reference_preflight_path=str(preflight),reference_preflight_sha256=sha(preflight),traces=traces,
        recording_python=platform.python_version(),recording_zlib=zlib.ZLIB_RUNTIME_VERSION,
        producer_source_sha256=sha('scripts/v5_prepare_trace.py'),helper_source_sha256=sha(__file__),
        scope='Gzip storage metadata only. Default producer compression is level9. Regenerate with pinned producer/runtime, then restore to a new file; original stored SHA must match. Full regeneration is not proved by recording headers. No serving calls or original-file modification.')
    with output.open('x') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    return result


def restore_copy(source,destination,entry):
    """Pure copy on new paths; reject payload/compressor differences and races."""
    source=Path(source);destination=Path(destination);partial=Path(str(destination)+'.partial')
    assert not destination.exists() and not partial.exists(),'Destination already exists; preserve inputs'
    assert uncompressed_sha(source)==entry['uncompressed_sha256'],'Regenerated plain bytes differ'
    raw=bytes.fromhex(entry['header_hex']);assert len(raw)==entry['header_bytes']
    # Parsing the captured header also catches malformed recipe boundaries.
    import io
    stream=io.BytesIO(raw);assert header(stream)==raw and stream.tell()==len(raw)
    created=False
    try:
        with source.open('rb') as src,partial.open('xb') as dst:
            created=True
            header(src);dst.write(raw);shutil.copyfileobj(src,dst)
        assert sha(partial)==entry['stored_sha256'],'DEFLATE bytes differ; retain originals or match the recorded producer/compressor'
        assert uncompressed_sha(partial)==entry['uncompressed_sha256']
        os.link(partial,destination)  # exclusive atomic publication, no overwrite
    finally:
        if created and partial.exists():partial.unlink()
    return dict(path=str(destination),stored_sha256=sha(destination),uncompressed_sha256=entry['uncompressed_sha256'])


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('record');c.add_argument('freeze',type=Path);c.add_argument('output',type=Path)
    r=sub.add_parser('restore');r.add_argument('recipe',type=Path);r.add_argument('original_path');r.add_argument('regenerated',type=Path);r.add_argument('destination',type=Path)
    a=p.parse_args()
    if a.command=='record':
        result=record(a.freeze,a.output);print('Recorded gzip headers',len(result['traces']),'original inputs unchanged');return
    recipe=json.loads(a.recipe.read_text());freeze,proof,preflight=reference(recipe['reference_freeze_path'])
    assert sha(recipe['reference_freeze_path'])==recipe['reference_freeze_sha256']
    assert str(preflight)==recipe['reference_preflight_path'] and sha(preflight)==recipe['reference_preflight_sha256']
    entry=recipe['traces'][a.original_path]
    assert entry['stored_sha256']==freeze['input_file_sha256'][a.original_path]==proof['inputs'][a.original_path]['stored_sha256']
    assert entry['uncompressed_sha256']==proof['inputs'][a.original_path]['uncompressed_sha256']
    print(json.dumps(restore_copy(a.regenerated,a.destination,entry),indent=2))


if __name__=='__main__':main()
