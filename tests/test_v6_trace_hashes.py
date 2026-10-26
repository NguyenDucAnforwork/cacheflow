import gzip
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from cacheflow.locomo import V2TraceRow,trace_digest
from v6_trace_hashes import CanonicalTraceDigest,scan


def rows():
    return [V2TraceRow(request_id=str(i),offset_ms=i,prompt='xin chào\n"quoted"',input_tokens=3,max_tokens=96,group='g',sample_id='s',qa_index=i,category=1,protocol='p_qa',checkpoint_session=None) for i in range(2)]


def test_streaming_canonical_matches_replay_not_jsonl_serialization(tmp_path):
    rr=rows();c=CanonicalTraceDigest()
    for r in rr:c.update(asdict(r))
    assert c.hexdigest()==c.hexdigest()==trace_digest(rr)
    raw=''.join(json.dumps(asdict(r),ensure_ascii=False)+'\n' for r in rr).encode()
    path=tmp_path/'trace.jsonl';path.write_bytes(raw);a=scan(path)
    compressed=tmp_path/'trace.jsonl.gz';compressed.write_bytes(gzip.compress(raw,mtime=0));b=scan(compressed)
    assert a['canonical_sha256']==b['canonical_sha256']==trace_digest(rr)
    assert a['uncompressed_sha256']==b['uncompressed_sha256']==hashlib.sha256(raw).hexdigest()
    assert a['stored_sha256']!=b['stored_sha256'] and a['uncompressed_sha256']!=a['canonical_sha256']
