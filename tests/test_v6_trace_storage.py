"""Small synthetic gzip copies; never mutate serving inputs or regenerate QA."""
import gzip
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_trace_storage import header,restore_copy,sha,uncompressed_sha


def write(path,payload,*,mtime,filename,level=9):
    with path.open('wb') as output:
        with gzip.GzipFile(filename=filename,mtime=mtime,compresslevel=level,fileobj=output,mode='wb') as stream:stream.write(payload)


def recipe(path):
    with path.open('rb') as stream:raw=header(stream)
    return dict(header_hex=raw.hex(),header_bytes=len(raw),stored_sha256=sha(path),uncompressed_sha256=uncompressed_sha(path))


def fixture(tmp_path):
    original=tmp_path/'reference.gz';regenerated=tmp_path/'regenerated.gz';payload=b'prefix-context '*10000+b'question-suffix '*8000
    write(original,payload,mtime=10,filename='original.jsonl')
    write(regenerated,payload,mtime=20,filename='different-name.jsonl')
    return original,regenerated,payload


def test_header_restoration_matches_original_stored_bytes_without_touching_inputs(tmp_path):
    original,regenerated,_=fixture(tmp_path);entry=recipe(original);old=sha(original);regen=sha(regenerated)
    assert old!=regen and uncompressed_sha(original)==uncompressed_sha(regenerated)
    target=tmp_path/'restored.gz';restore_copy(regenerated,target,entry)
    assert target.read_bytes()==original.read_bytes() and sha(original)==old and sha(regenerated)==regen
    with pytest.raises(AssertionError,match='Destination already'):restore_copy(regenerated,target,entry)


def test_payload_or_compressor_changes_are_not_accepted_as_metadata(tmp_path):
    original,regenerated,payload=fixture(tmp_path);entry=recipe(original);target=tmp_path/'restored.gz'
    write(regenerated,payload+b'changed',mtime=20,filename='different-name.jsonl')
    with pytest.raises(AssertionError,match='plain bytes differ'):restore_copy(regenerated,target,entry)
    write(regenerated,payload,mtime=20,filename='different-name.jsonl',level=1)
    with pytest.raises(AssertionError,match='DEFLATE bytes differ'):restore_copy(regenerated,target,entry)
    assert not target.exists() and not Path(str(target)+'.partial').exists()


def test_publication_race_preserves_someone_elses_destination(tmp_path,monkeypatch):
    original,regenerated,_=fixture(tmp_path);target=tmp_path/'restored.gz'
    def race(source,destination):
        Path(destination).write_bytes(b'other writer')
        raise FileExistsError('Simulated publication race')
    monkeypatch.setattr('v6_trace_storage.os.link',race)
    with pytest.raises(FileExistsError):restore_copy(regenerated,target,recipe(original))
    assert target.read_bytes()==b'other writer' and not Path(str(target)+'.partial').exists()
