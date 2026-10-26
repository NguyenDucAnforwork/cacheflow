import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_raw_archive import archive,expanded,sha


def files(tmp_path):
    raw=tmp_path/'x.outputs.jsonl';content=(b'{"output":"retained answer"}\n'*1000)+b'final bytes\r\n';raw.write_bytes(content)
    audit=tmp_path/'audit.json';audit.write_text(json.dumps(dict(complete=True,raw_sha256={str(raw):sha(raw)})))
    return raw,content,audit,tmp_path/'archive.json'


def test_raw_roundtrip_and_temporary_expansion(tmp_path):
    raw,content,audit,manifest=files(tmp_path);record=archive(audit,manifest)
    assert not raw.exists() and record['files'][0]['archive_bytes']<len(content)
    with expanded(manifest):assert raw.read_bytes()==content
    assert not raw.exists()
    with pytest.raises(AssertionError):archive(audit,manifest)


def test_no_archival_before_complete_audit_or_hash_match(tmp_path):
    raw,content,audit,manifest=files(tmp_path)
    audit.write_text(json.dumps(dict(complete=False,raw_sha256={str(raw):sha(raw)})))
    with pytest.raises(AssertionError):archive(audit,manifest)
    assert raw.read_bytes()==content and not Path(str(raw)+'.gz').exists()
    audit.write_text(json.dumps(dict(complete=True,raw_sha256={str(raw):'wrong'})))
    with pytest.raises(AssertionError):archive(audit,manifest)
    assert raw.read_bytes()==content


def test_corrupted_archive_or_changed_audit_rejected(tmp_path):
    raw,content,audit,manifest=files(tmp_path);data=archive(audit,manifest)
    audit.write_text(audit.read_text()+'\n')
    with pytest.raises(AssertionError):
        with expanded(manifest):pass
    assert not raw.exists()
    audit.write_text(audit.read_text()[:-1])
    Path(data['files'][0]['archive']).write_bytes(b'broken gzip')
    with pytest.raises(AssertionError):
        with expanded(manifest):pass
    assert not raw.exists()


def test_preexisting_matching_plain_file_is_retained(tmp_path):
    raw,content,audit,manifest=files(tmp_path);archive(audit,manifest);raw.write_bytes(content)
    with expanded(manifest):assert raw.read_bytes()==content
    assert raw.read_bytes()==content
