import json

import pytest

from cacheflow.analyze import compare


def _write_run(path, run_id, ttft, output_hash="same", trace="trace"):
    row = {"request_id": "request-1", "group": "doc-1", "status": "ok", "trace_sha256": trace,
           "prompt_sha256": "prompt", "input_tokens": 2048, "arrival_ttft_ms": ttft,
           "output_hash": output_hash}
    path.write_text(json.dumps(row) + "\n")
    path.with_suffix(".summary.json").write_text(json.dumps({"run_id": run_id, "output_tokens_per_s": 10}))


def test_paired_analysis_checks_prompt_and_counts_output_deviation(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    _write_run(a, "fifo", 200)
    _write_run(b, "dhas", 150, output_hash="changed")
    result = compare(a, b)
    assert result["paired_ttft_mean_delta_ms"] == -50
    assert result["output_hash_mismatches"] == 1
    _write_run(b, "dhas", 150, trace="other")
    with pytest.raises(ValueError, match="trace hashes"):
        compare(a, b)
