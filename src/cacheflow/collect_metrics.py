"""Low-rate host/GPU/cache metrics sampler for causal benchmark interpretation."""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import time
from pathlib import Path

import httpx
import psutil

NAMES = (
    "vllm:prefix_cache_hits_total",
    "vllm:external_prefix_cache_hits_total",
    "vllm:prompt_tokens_total",
    "vllm:prompt_tokens_cached_total",
    "vllm:request_prefill_kv_computed_tokens_sum",
    "vllm:kv_cache_usage_perc",
    "vllm:num_requests_running",
    "vllm:num_requests_waiting",
    "vllm:request_queue_time_seconds_sum",
    "vllm:request_queue_time_seconds_count",
    "vllm:time_to_first_token_seconds_sum",
    "vllm:time_to_first_token_seconds_count",
    "vllm:request_prefill_time_seconds_sum",
    "vllm:request_prefill_time_seconds_count",
    "vllm:iteration_tokens_total_sum",
    "vllm:iteration_tokens_total_count",
    "vllm:num_preemptions_total",
    "lmcache_mp_l1_read_chunks_total",
    "lmcache_mp_l1_write_chunks_total",
    "lmcache_mp_l1_evicted_chunks_total",
    "lmcache_mp_num_chunks_loaded_total",
    "lmcache_mp_l1_memory_usage_bytes",
    "lmcache_mp_num_submitted_retrieves_total",
    "lmcache_mp_num_finished_retrieves_total",
    "lmcache_mp_l0_l1_retrieve_throughput_GB_per_second_sum",
    "lmcache_mp_l0_l1_retrieve_throughput_GB_per_second_count",
)


def parse_metrics(text: str) -> dict[str, float]:
    values = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        name = line.split("{", 1)[0].split(" ", 1)[0]
        if name in NAMES:
            try:
                values[name] = values.get(name, 0.0) + float(line.rsplit(" ", 1)[1])
            except ValueError:
                pass
    return values


def gpu_snapshot() -> dict:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,clocks.sm,temperature.gpu,power.draw",
         "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4,
    )
    if result.returncode:
        return {"error": result.stderr.strip()[:150]}
    items = [float(x.strip()) for x in result.stdout.splitlines()[0].split(",")]
    return dict(zip(("gpu_util_pct", "gpu_memory_util_pct", "vram_used_mib", "vram_total_mib",
                     "sm_clock_mhz", "temperature_c", "power_w"), items))


def process_snapshot() -> dict:
    result = {}
    for process in psutil.process_iter(["pid", "name", "cmdline", "memory_info", "num_ctx_switches", "cpu_times"]):
        try:
            cmd = " ".join(process.info.get("cmdline") or [])
            name = "vllm" if "vllm serve" in cmd else "lmcache" if "lmcache server" in cmd else "gateway" if "cacheflow.gateway:create_app" in cmd else None
            if name:
                entry = result.setdefault(name, {"rss_bytes": 0, "processes": 0, "ctx_switches": 0, "cpu_seconds": 0.0})
                entry["rss_bytes"] += process.info["memory_info"].rss
                entry["processes"] += 1
                switches = process.info["num_ctx_switches"]
                entry["ctx_switches"] += switches.voluntary + switches.involuntary
                times = process.info["cpu_times"]
                entry["cpu_seconds"] += times.user + times.system
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    psutil.cpu_percent(interval=None)
    with httpx.Client(timeout=3) as client, path.open("w", encoding="utf-8") as file:
        while running:
            now = time.monotonic_ns()
            record = {"timestamp_ns": now, "cpu_percent": psutil.cpu_percent(interval=None),
                      "memory_available_bytes": psutil.virtual_memory().available,
                      "process": process_snapshot(), "gpu": gpu_snapshot()}
            for label, url in (("vllm", "http://127.0.0.1:8000/metrics"),
                               ("lmcache", "http://127.0.0.1:18080/metrics")):
                try:
                    response = client.get(url)
                    record[label] = parse_metrics(response.text) if response.status_code == 200 else {"http_status": response.status_code}
                except httpx.HTTPError as exc:
                    record[label] = {"error": type(exc).__name__}
            file.write(json.dumps(record, sort_keys=True) + "\n")
            file.flush()
            time.sleep(max(0.0, args.interval - (time.monotonic_ns() - now) / 1e9))


if __name__ == "__main__":
    main()
