"""Fixed-arrival streaming replay; records original-arrival end-to-end clocks."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import subprocess
import time
from pathlib import Path

import httpx
from transformers import AutoTokenizer

from .data import build_trace, trace_digest
from .real_workload import load_trace


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct / 100
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


async def replay(args: argparse.Namespace) -> dict:
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True, trust_remote_code=False)
    if args.trace_file:
        rows, trace_sha = load_trace(args.trace_file)
    else:
        rows = build_trace(tokenizer, workload=args.workload, seed=args.seed, target_input_tokens=args.input_tokens,
                           groups=args.groups, per_group=args.per_group, output_tokens=args.output_tokens)
        trace_sha = trace_digest(rows)
    real = bool(args.trace_file)
    engine = _engine_info() if real else {}
    commit_sha = subprocess.check_output(["git", "-C", "/workspace", "rev-parse", "HEAD"], text=True).strip()
    mode = Path("/workspace/.cacheflow-mode").read_text().strip() if Path("/workspace/.cacheflow-mode").exists() else "unknown"
    policy = Path("/workspace/.cacheflow-policy").read_text().strip() if Path("/workspace/.cacheflow-policy").exists() else "unknown"
    base_ns = time.monotonic_ns() + 2_000_000_000
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    texts = []
    timeout = httpx.Timeout(connect=30, read=600, write=30, pool=30)
    async with httpx.AsyncClient(timeout=timeout, limits=httpx.Limits(max_connections=128)) as client:
        async def send(row):
            due_ns = base_ns + row.offset_ms * 1_000_000
            remaining = (due_ns - time.monotonic_ns()) / 1e9
            if remaining > 0:
                await asyncio.sleep(remaining)
            dispatch_client_ns = time.monotonic_ns()
            body = {"model": args.model_name, "prompt": row.prompt, "max_tokens": row.max_tokens,
                    "temperature": 0, "stream": True, "add_special_tokens": False,
                    "stream_options": {"include_usage": True}}
            headers = {"X-Cacheflow-Request-ID": row.request_id, "X-Cacheflow-Arrival-Ns": str(due_ns),
                       "X-Cacheflow-Run-ID": args.run_id}
            if real:
                headers["X-Cacheflow-Class"] = row.cls
            first_ns = None
            token_events = []
            pieces = []
            usage = None
            status = "ok"
            http_status = None
            try:
                async with client.stream("POST", args.url.rstrip("/") + "/v1/completions", json=body, headers=headers) as response:
                    http_status = response.status_code
                    if response.status_code != 200:
                        status = f"http_{response.status_code}"
                        await response.aread()
                    else:
                        async for line in response.aiter_lines():
                            if not line.startswith("data: ") or line == "data: [DONE]":
                                continue
                            try:
                                event = json.loads(line[6:])
                            except json.JSONDecodeError:
                                continue
                            if event.get("usage"):
                                usage = event["usage"]
                            for choice in event.get("choices", []):
                                part = choice.get("text") or choice.get("delta", {}).get("content")
                                if part:
                                    now = time.monotonic_ns()
                                    if first_ns is None:
                                        first_ns = now
                                    token_events.append(now)
                                    pieces.append(part)
            except Exception as exc:
                status = f"exception:{type(exc).__name__}"
            done_ns = time.monotonic_ns()
            if first_ns is None and status == "ok":
                status = "empty_response"
            output_tokens = usage.get("completion_tokens") if usage else len(tokenizer.encode("".join(pieces), add_special_tokens=False))
            output_tokens = int(output_tokens or 0)
            tpot_ms = (done_ns - first_ns) / 1e6 / (output_tokens - 1) if first_ns and output_tokens > 1 else None
            record = {
                "run_id": args.run_id, "request_id": row.request_id, "group": row.group,
                "workload": args.workload, "trace_sha256": trace_sha,
                "prompt_sha256": hashlib.sha256(row.prompt.encode()).hexdigest(),
                "scheduled_arrival_ns": due_ns, "client_send_ns": dispatch_client_ns,
                "first_token_ns": first_ns, "complete_ns": done_ns,
                "arrival_ttft_ms": (first_ns - due_ns) / 1e6 if first_ns else None,
                "client_ttft_ms": (first_ns - dispatch_client_ns) / 1e6 if first_ns else None,
                "latency_ms": (done_ns - due_ns) / 1e6,
                "tpot_ms": tpot_ms,
                "input_tokens": row.input_tokens, "server_prompt_tokens": usage.get("prompt_tokens") if usage else None,
                "output_tokens": output_tokens, "usage_reported": usage is not None,
                "stream_events": len(token_events),
                "output_hash": hashlib.sha256("".join(pieces).encode()).hexdigest(),
                "status": status, "http_status": http_status,
            }
            if real:
                gaps = [(b - a) / 1e6 for a, b in zip(token_events, token_events[1:])]
                record["max_itl_ms"] = max(gaps) if gaps else None
                record.update({"cls": row.cls, "max_tokens": row.max_tokens, "gold_letter": row.gold_letter, "source_id": row.source_id})
                texts.append({"request_id": row.request_id, "cls": row.cls, "gold_letter": row.gold_letter, "output_text": "".join(pieces)})
            records.append(record)

        await asyncio.gather(*(send(row) for row in rows))
    with output_path.open("w", encoding="utf-8") as file:
        for record in sorted(records, key=lambda item: item["request_id"]):
            file.write(json.dumps(record, sort_keys=True) + "\n")
    if real:
        with output_path.with_suffix(".outputs.jsonl").open("w", encoding="utf-8") as file:
            for item in sorted(texts, key=lambda t: t["request_id"]):
                file.write(json.dumps(item, sort_keys=True) + "\n")
    ttft = [r["arrival_ttft_ms"] for r in records if r["arrival_ttft_ms"] is not None]
    tpot = [r["tpot_ms"] for r in records if r["tpot_ms"] is not None]
    duration_s = (max(r["complete_ns"] for r in records) - base_ns) / 1e9
    summary = {
        "run_id": args.run_id, "workload": args.workload, "trace_sha256": trace_sha,
        "git_sha": commit_sha, "mode": mode, "policy": policy,
        "seed": args.seed, "input_tokens_target": args.input_tokens,
        "output_tokens_budget": args.output_tokens, "groups": args.groups, "per_group": args.per_group,
        "requests": len(records), "successes": sum(r["status"] == "ok" for r in records),
        "arrival_ttft_p50_ms": _percentile(ttft, 50), "arrival_ttft_p90_ms": _percentile(ttft, 90),
        "arrival_ttft_p99_ms": _percentile(ttft, 99),
        "tpot_p50_ms": _percentile(tpot, 50), "tpot_p90_ms": _percentile(tpot, 90),
        "output_tokens_per_s": sum(r["output_tokens"] for r in records) / duration_s,
        "requests_per_s": len(records) / duration_s,
        "duration_s": duration_s,
        "raw_path": str(output_path),
    }
    if real:
        summary.update({"trace_file": args.trace_file, "gpu_kv_bytes_marker": _marker("/workspace/.cacheflow-gpu-kv-bytes"),
                        "max_num_batched_tokens_marker": _marker("/workspace/.cacheflow-mnbt"), **engine})
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    registry_path = Path(args.registry)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    row = {key: value for key, value in summary.items() if key != "raw_path"}
    row["raw_path"] = str(output_path)
    row["summary_path"] = str(summary_path)
    row["metrics_path"] = str(output_path.with_suffix(".metrics.jsonl"))
    if registry_path.exists():
        with registry_path.open(newline="") as file:
            if args.run_id in {existing["run_id"] for existing in csv.DictReader(file)}:
                raise ValueError(f"duplicate run_id: {args.run_id}")
    with registry_path.open("a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(row), lineterminator="\n")
        if file.tell() == 0:
            writer.writeheader()
        writer.writerow(row)
    print(json.dumps(summary, sort_keys=True, indent=2))
    return summary


def _marker(path: str) -> str | None:
    return Path(path).read_text().strip() if Path(path).exists() else None


def _engine_info() -> dict:
    """Effective engine settings and KV capacity as reported by the running vLLM server."""
    info: dict = {}
    try:
        text = httpx.get("http://127.0.0.1:8000/metrics", timeout=5).text
        for line in text.splitlines():
            if line.startswith("vllm:cache_config_info"):
                labels = dict(part.split("=", 1) for part in line[line.index("{") + 1:line.rindex("}")].split(","))
                blocks = int(labels["num_gpu_blocks"].strip('"'))
                size = int(labels["block_size"].strip('"'))
                info.update({"engine_num_gpu_blocks": blocks, "engine_block_size": size, "engine_gpu_kv_tokens": blocks * size})
        config = httpx.get("http://127.0.0.1:8000/server_info", params={"config_format": "json"}, timeout=5).json()
        sched = (config.get("vllm_config") or config).get("scheduler_config") or {}
        for key in ("max_num_batched_tokens", "max_num_seqs", "enable_chunked_prefill", "chunked_prefill_enabled"):
            if key in sched:
                info[f"engine_{key}"] = sched[key]
        if isinstance(config.get("vllm_config"), str):
            info["engine_server_info_note"] = "vllm_config returned as string"
    except Exception as exc:  # engine info is best-effort; never fail the benchmark
        info["engine_info_error"] = type(exc).__name__
    return info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8100")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--model-name", default="cacheflow-qwen3-1.7b")
    parser.add_argument("--workload", choices=["long_doc", "long_doc_revisit", "long_doc_simultaneous", "multi_turn", "distinct", "real_quality_chat"], required=True)
    parser.add_argument("--trace-file", default=None, help="JSONL trace from cacheflow.real_workload (real_quality_chat)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--input-tokens", type=int, default=4096)
    parser.add_argument("--output-tokens", type=int, default=64)
    parser.add_argument("--groups", type=int, default=8)
    parser.add_argument("--per-group", type=int, default=4)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--registry", default="/workspace/results/registry.csv")
    args = parser.parse_args()
    asyncio.run(replay(args))


if __name__ == "__main__":
    main()
