"""Guardrails for interpreting matched E1 crossover artifacts."""
import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "v2_compare_e1", Path(__file__).resolve().parents[1] / "scripts/v2_compare_e1.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def arm(mode, policy, ttft):
    summary = {
        "run_id": mode, "mode": mode, "policy": policy,
        "trace_sha256": "trace", "model_revision": "revision", "model_name": "model",
        "gpu_kv_bytes": 8, "max_model_len": 32768, "output_tokens_budget": 32,
        "source_sha256": "source", "prompt_version": "v1", "protocol": "probe",
        "arrival": "open-loop", "vllm_version": "0.22.0",
        "lmcache_version": "0.5.3", "transformers_version": "5.6.2",
        "engine_pid": 123, "lmcache_pid": 456, "arrival_ttft_p50_ms": ttft,
    }
    requests = {
        "probe-00-producer": {"prompt_sha256": "a", "arrival_ttft_ms": ttft},
        "probe-00-follower": {"prompt_sha256": "b", "arrival_ttft_ms": ttft},
    }
    gateway = {key: {"admission_wait_ms": 0, "delay_hit_candidate": False}
               for key in requests}
    metrics = {"counter_deltas": {"vllm": {}, "lmcache": {}}}
    return {"summary": summary, "requests": requests,
            "gateway": gateway, "metrics": metrics}


def test_matched_pair_reports_paired_follower_latency():
    b2, b3 = arm("B2", "fifo", 100), arm("B3", "dhas", 80)
    result = module.compare(b2, b3)
    assert result["requests"] == 2
    assert result["follower_ttft_delta_median_ms"] == -20
    assert result["paired_requests"][0]["delta_b3_minus_b2_ms"] == -20


def test_reject_changed_serving_process_or_trace():
    b2, b3 = arm("B2", "fifo", 100), arm("B3", "dhas", 80)
    changed = copy.deepcopy(b3)
    changed["summary"]["engine_pid"] = 999
    with pytest.raises(ValueError, match="serving process changed"):
        module.compare(b2, changed)
    changed = copy.deepcopy(b3)
    changed["summary"]["trace_sha256"] = "different"
    with pytest.raises(ValueError, match="unmatched run metadata"):
        module.compare(b2, changed)
