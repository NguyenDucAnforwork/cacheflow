"""Open-loop replay of a frozen V2 JSONL trace against an OpenAI completion API."""

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

from .locomo import V2TraceRow, trace_digest


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct / 100
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def load_trace(path: Path) -> list[V2TraceRow]:
    rows = [V2TraceRow(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        raise ValueError("empty trace")
    if len({row.request_id for row in rows}) != len(rows):
        raise ValueError("duplicate request ID")
    if any(row.offset_ms < 0 for row in rows):
        raise ValueError("negative arrival offset")
    if rows != sorted(rows, key=lambda row: row.offset_ms):
        raise ValueError("trace arrivals are not ordered")
    return rows


async def replay(args: argparse.Namespace) -> dict:
    rows = load_trace(args.trace)
    trace_sha = trace_digest(rows)
    manifest_path = args.trace.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if manifest and manifest.get("trace_sha256") != trace_sha:
        raise ValueError("trace SHA does not match manifest")
    registry = args.registry
    if registry.exists():
        with registry.open(newline="") as file:
            if args.run_id in {row["run_id"] for row in csv.DictReader(file)}:
                raise ValueError(f"duplicate run ID: {args.run_id}")
    root = Path(__file__).resolve().parents[2]
    git_sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    base_ns = time.monotonic_ns() + 2_000_000_000
    records: list[dict] = []
    outputs: list[dict] = []
    timeout = httpx.Timeout(connect=30, read=600, write=30, pool=600)
    async with httpx.AsyncClient(timeout=timeout, limits=httpx.Limits(max_connections=256)) as client:
        async def send(row: V2TraceRow) -> None:
            due_ns = base_ns + row.offset_ms * 1_000_000
            delay = (due_ns - time.monotonic_ns()) / 1e9
            if delay > 0:
                await asyncio.sleep(delay)
            send_ns = time.monotonic_ns()
            first_ns = None
            chunks: list[str] = []
            usage = None
            status = "ok"
            http_status = None
            body = {"model": args.model_name, "prompt": row.prompt,
                    "max_tokens": row.max_tokens, "temperature": 0,
                    "stream": True, "add_special_tokens": False,
                    "stream_options": {"include_usage": True}}
            headers = {"X-Cacheflow-Request-ID": row.request_id,
                       "X-Cacheflow-Arrival-Ns": str(due_ns),
                       "X-Cacheflow-Run-ID": args.run_id}
            try:
                async with client.stream("POST", args.url.rstrip("/") + "/v1/completions",
                                         json=body, headers=headers) as response:
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
                                    first_ns = now if first_ns is None else first_ns
                                    chunks.append(part)
            except Exception as exc:
                status = f"exception:{type(exc).__name__}"
            done_ns = time.monotonic_ns()
            if first_ns is None and status == "ok":
                status = "empty_response"
            output = "".join(chunks)
            output_tokens = usage.get("completion_tokens") if usage else None
            record = {
                "run_id": args.run_id, "request_id": row.request_id,
                "sample_id": row.sample_id, "qa_index": row.qa_index,
                "category": row.category, "protocol": row.protocol,
                "checkpoint_session": row.checkpoint_session,
                "trace_sha256": trace_sha,
                "prompt_sha256": hashlib.sha256(row.prompt.encode()).hexdigest(),
                "scheduled_arrival_ns": due_ns, "client_send_ns": send_ns,
                "first_token_ns": first_ns, "complete_ns": done_ns,
                "arrival_ttft_ms": (first_ns - due_ns) / 1e6 if first_ns else None,
                "client_ttft_ms": (first_ns - send_ns) / 1e6 if first_ns else None,
                "latency_ms": (done_ns - due_ns) / 1e6,
                "input_tokens": row.input_tokens,
                "server_prompt_tokens": usage.get("prompt_tokens") if usage else None,
                "output_tokens": output_tokens, "usage_reported": usage is not None,
                "output_hash": hashlib.sha256(output.encode()).hexdigest(),
                "status": status, "http_status": http_status,
            }
            records.append(record)
            if args.capture_text:
                outputs.append({"run_id": args.run_id, "request_id": row.request_id,
                                "output": output, "status": status})

        await asyncio.gather(*(send(row) for row in rows))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        for record in sorted(records, key=lambda item: item["request_id"]):
            file.write(json.dumps(record, sort_keys=True) + "\n")
    if args.capture_text:
        with args.output.with_suffix(".outputs.jsonl").open("w", encoding="utf-8") as file:
            for output in sorted(outputs, key=lambda item: item["request_id"]):
                file.write(json.dumps(output, sort_keys=True) + "\n")
    successful = [record for record in records if record["status"] == "ok"]
    ttft = [record["arrival_ttft_ms"] for record in successful]
    duration_s = (max(record["complete_ns"] for record in records) - base_ns) / 1e9
    summary = {
        "run_id": args.run_id, "git_sha": git_sha, "trace_sha256": trace_sha,
        "source_sha256": manifest.get("source_sha256"),
        "prompt_version": manifest.get("prompt_version"),
        "protocol": manifest.get("protocol"), "arrival": manifest.get("arrival"),
        "model_name": args.model_name, "url": args.url,
        "requests": len(records), "successes": len(successful),
        "arrival_ttft_p50_ms": _percentile(ttft, 50),
        "arrival_ttft_p95_ms": _percentile(ttft, 95),
        "arrival_ttft_p99_ms": _percentile(ttft, 99),
        "requests_per_s": len(successful) / duration_s if duration_s > 0 else None,
        "duration_s": duration_s,
        "raw_path": str(args.output),
    }
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    registry.parent.mkdir(parents=True, exist_ok=True)
    with registry.open("a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary) + ["summary_path"], lineterminator="\n")
        if file.tell() == 0:
            writer.writeheader()
        writer.writerow({**summary, "summary_path": str(summary_path)})
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8100")
    parser.add_argument("--model-name", default="cacheflow-qwen3-1.7b")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=Path("results/v2/registry.csv"))
    parser.add_argument("--capture-text", action="store_true")
    asyncio.run(replay(parser.parse_args()))


if __name__ == "__main__":
    main()
