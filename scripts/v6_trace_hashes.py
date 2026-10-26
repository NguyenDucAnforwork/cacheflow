"""Keep stored bytes, uncompressed JSONL bytes and replay canonical digest distinct."""
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from cacheflow.locomo import V2TraceRow


class CanonicalTraceDigest:
    """Streaming equivalent of cacheflow.locomo.trace_digest's JSON array."""
    def __init__(self):self.digest=hashlib.sha256(b'[');self.requests=0
    def update(self,row):
        normalized=asdict(V2TraceRow(**row))
        if self.requests:self.digest.update(b',')
        self.digest.update(json.dumps(normalized,sort_keys=True,separators=(',',':')).encode())
        self.requests+=1
    def hexdigest(self):
        final=self.digest.copy();final.update(b']');return final.hexdigest()


def scan(path):
    path=Path(path)
    with path.open('rb') as f:stored=hashlib.file_digest(f,'sha256').hexdigest()
    plain=hashlib.sha256();canonical=CanonicalTraceDigest();opener=gzip.open if path.suffix=='.gz' else open
    with opener(path,'rb') as f:
        for line in f:
            plain.update(line)
            if line.strip():canonical.update(json.loads(line))
    return dict(stored_sha256=stored,uncompressed_sha256=plain.hexdigest(),canonical_sha256=canonical.hexdigest(),requests=canonical.requests)
