import json

import pytest

from cacheflow.v2_metrics import summarize


def test_counter_deltas_and_peak_memory(tmp_path):
    path = tmp_path / "metrics.jsonl"
    rows = [
        {"timestamp_ns": 100, "vllm": {"vllm:prompt_tokens_total": 12,
          "vllm:request_prefill_kv_computed_tokens_sum": 10},
         "lmcache": {"lmcache_mp_num_chunks_loaded_total": 2},
         "gpu": {"vram_used_mib": 4000}, "memory_available_bytes": 9000},
        {"timestamp_ns": 2_000_000_100, "vllm": {"vllm:prompt_tokens_total": 32,
          "vllm:request_prefill_kv_computed_tokens_sum": 18},
         "lmcache": {"lmcache_mp_num_chunks_loaded_total": 5},
         "gpu": {"vram_used_mib": 5000}, "memory_available_bytes": 8000},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    result = summarize(path)
    assert result["counter_deltas"]["vllm"]["vllm:prompt_tokens_total"] == 20
    assert result["counter_deltas"]["vllm"]["vllm:request_prefill_kv_computed_tokens_sum"] == 8
    assert result["counter_deltas"]["lmcache"]["lmcache_mp_num_chunks_loaded_total"] == 3
    assert result["vram_peak_mib"] == 5000
    assert result["host_memory_available_min_bytes"] == 8000


def test_counter_reset_invalidates_run(tmp_path):
    path = tmp_path / "reset.jsonl"
    path.write_text("\n".join(json.dumps({"timestamp_ns": t,
        "vllm": {"vllm:prompt_tokens_total": v}}) for t, v in [(1, 10), (2, 3)]) + "\n")
    with pytest.raises(ValueError, match="counter reset"):
        summarize(path)


def test_counter_absent_at_healthy_baseline_starts_at_zero(tmp_path):
    path = tmp_path / "late_counter.jsonl"
    rows = [
        {"timestamp_ns": 1, "lmcache": {"lmcache_mp_l1_memory_usage_bytes": 0}},
        {"timestamp_ns": 2, "lmcache": {"lmcache_mp_num_chunks_loaded_total": 3}},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    assert summarize(path)["counter_deltas"]["lmcache"]["lmcache_mp_num_chunks_loaded_total"] == 3
    rows[0]["lmcache"] = {"error": "ConnectError"}
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    assert summarize(path)["counter_deltas"]["lmcache"]["lmcache_mp_num_chunks_loaded_total"] is None
