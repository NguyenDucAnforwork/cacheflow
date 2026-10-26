import json
from dataclasses import asdict

import pytest

from cacheflow.locomo import V2TraceRow
from cacheflow.v2_replay import load_trace


def row(request_id, offset_ms):
    return V2TraceRow(request_id, offset_ms, "Question:\nTest\nAnswer:", 6, 4,
                      "sample", "sample", 0, 1, "p_qa", None)


def test_trace_loader_rejects_duplicate_or_unsorted_arrivals(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(json.dumps(asdict(item)) for item in [row("a", 1), row("b", 2)]) + "\n")
    assert [item.request_id for item in load_trace(path)] == ["a", "b"]
    path.write_text("\n".join(json.dumps(asdict(item)) for item in [row("a", 2), row("b", 1)]) + "\n")
    with pytest.raises(ValueError, match="not ordered"):
        load_trace(path)
    path.write_text("\n".join(json.dumps(asdict(item)) for item in [row("a", 1), row("a", 2)]) + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_trace(path)


def test_gzip_trace_has_same_rows_as_plain_trace(tmp_path):
    import gzip
    text='\n'.join(json.dumps(asdict(x)) for x in [row('a',1),row('b',2)])+'\n'
    plain=tmp_path/'trace.jsonl';packed=tmp_path/'trace.jsonl.gz'
    plain.write_text(text)
    with gzip.open(packed,'wt') as f:f.write(text)
    assert load_trace(plain)==load_trace(packed)
