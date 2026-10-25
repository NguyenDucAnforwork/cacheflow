import json

import pytest

from cacheflow.locomo import build_trace, context_prefix, load_locomo, trace_digest


class WordTokenizer:
    def encode(self, text, *, add_special_tokens):
        assert not add_special_tokens
        return text.split()


def fixture_source(tmp_path):
    data = []
    for sample in ("conv-a", "conv-b"):
        data.append({
            "sample_id": sample,
            "conversation": {
                "speaker_a": "Alex", "speaker_b": "Blair",
                "session_1_date_time": "day 1",
                "session_1": [{"dia_id": "D1:1", "speaker": "Alex", "text": "first fact"}],
                "session_2_date_time": "day 2",
                "session_2": [{"dia_id": "D2:1", "speaker": "Blair", "text": "future fact",
                               "blip_caption": "a photograph"}],
            },
            "qa": [
                {"question": "What came first?", "answer": "first fact", "category": 1,
                 "evidence": ["D1:1"]},
                {"question": "What came later?", "answer": "future fact", "category": 2,
                 "evidence": ["D2:1"]},
            ],
        })
    path = tmp_path / "locomo.json"
    path.write_text(json.dumps(data))
    return path


def test_session_prompt_excludes_future_content_and_gold(tmp_path):
    conversations = load_locomo(fixture_source(tmp_path))
    rows, manifest = build_trace(conversations, WordTokenizer(), protocol="p_session", qps=2,
                                 max_model_len=100, output_tokens=5)
    first = next(row for row in rows if row.request_id == "conv-a-q000")
    assert first.checkpoint_session == 1
    assert "future fact" not in first.prompt
    assert "day 2" not in first.prompt
    assert "first fact\nAnswer:" not in first.prompt
    assert manifest["requests"] == 4


def test_trace_order_fit_and_digest_are_deterministic(tmp_path):
    conversations = load_locomo(fixture_source(tmp_path))
    args = dict(protocol="p_qa", arrival="interleaved", qps=3,
                max_model_len=100, output_tokens=5, seed=11)
    rows, manifest = build_trace(conversations, WordTokenizer(), **args)
    again, _ = build_trace(conversations, WordTokenizer(), **args)
    assert [row.request_id for row in rows] == ["conv-a-q000", "conv-b-q000",
                                                 "conv-a-q001", "conv-b-q001"]
    assert rows == again
    assert trace_digest(rows) == manifest["trace_sha256"]
    assert all(row.input_tokens + row.max_tokens <= 100 for row in rows)
    with pytest.raises(ValueError, match="unknown sample"):
        build_trace(conversations, WordTokenizer(), sample_ids=("missing",))


def test_malformed_evidence_kept_for_audit_but_not_checkpoint(tmp_path):
    path = fixture_source(tmp_path)
    data = json.loads(path.read_text())
    data[0]["qa"][0]["evidence"] = ["D:1:1"]
    path.write_text(json.dumps(data))
    conversations = load_locomo(path)
    assert conversations[0].questions[0].evidence_raw == ("D:1:1",)
    assert not conversations[0].questions[0].evidence_valid
    rows, manifest = build_trace(conversations, WordTokenizer(), protocol="p_session",
                                 max_model_len=100, output_tokens=5)
    assert "conv-a-q000" not in {row.request_id for row in rows}
    assert manifest["excluded"]["no_evidence"] == 1
