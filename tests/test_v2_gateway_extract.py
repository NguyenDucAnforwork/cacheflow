import json

import pytest

from scripts.v2_extract_gateway import extract


def test_gateway_extract_rejects_missing_and_duplicate_rows(tmp_path):
    requests = tmp_path / "requests.jsonl"
    gateway = tmp_path / "gateway.jsonl"
    output = tmp_path / "run.gateway.jsonl"
    requests.write_text(''.join(json.dumps({"request_id": key}) + "\n" for key in ("a", "b")))
    gateway.write_text(''.join(json.dumps(row) + "\n" for row in (
        {"run_id": "other", "request_id": "x"},
        {"run_id": "run", "request_id": "b", "dispatch_ns": 2},
        {"run_id": "run", "request_id": "a", "dispatch_ns": 1},
    )))
    assert extract(gateway, requests, "run", output) == 2
    assert [json.loads(line)["request_id"] for line in output.read_text().splitlines()] == ["a", "b"]
    gateway.write_text(gateway.read_text() + json.dumps({"run_id": "run", "request_id": "a"}) + "\n")
    with pytest.raises(ValueError, match="mismatch"):
        extract(gateway, requests, "run", output)
