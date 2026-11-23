"""Streaming OpenAI completions proxy with auditable admission timing."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from transformers import AutoTokenizer

from .prefix import prefix_blocks
from .scheduler import AdmissionScheduler, Ticket


def _first_content_token(buffer: bytearray, chunk: bytes) -> bool:
    """Consume complete SSE lines and return whether any contains generated text."""
    buffer.extend(chunk)
    seen = False
    while b"\n" in buffer:
        line, _, remainder = buffer.partition(b"\n")
        buffer[:] = remainder
        if not line.startswith(b"data: ") or line == b"data: [DONE]":
            continue
        try:
            event = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        for choice in event.get("choices", []):
            text = choice.get("text") or choice.get("delta", {}).get("content")
            if text:
                seen = True
    return seen


class TraceWriter:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def append(self, record: dict[str, Any]) -> None:
        async with self._lock:
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def create_app(config_path: str | None = None) -> FastAPI:
    settings = yaml.safe_load(Path(config_path or os.environ.get("CACHEFLOW_POLICY_CONFIG", "/workspace/configs/policies.yaml")).read_text())
    if os.environ.get("CACHEFLOW_POLICY"):
        settings["scheduler"]["policy"] = os.environ["CACHEFLOW_POLICY"]
    model = settings["model"]
    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True, trust_remote_code=False)
    if os.environ.get("CACHEFLOW_AGE_CAP_MS"):
        settings["scheduler"]["age_cap_ms"] = int(os.environ["CACHEFLOW_AGE_CAP_MS"])
    scheduler = AdmissionScheduler(**settings["scheduler"])
    trace = TraceWriter(os.environ.get("CACHEFLOW_TRACE", "/workspace/results/raw/gateway.jsonl"))
    upstream = settings.get("upstream", "http://127.0.0.1:8000").rstrip("/")
    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=30, read=600, write=30, pool=30), limits=httpx.Limits(max_connections=128))
    app = FastAPI(title="CacheFlow Gateway")
    app.state.scheduler = scheduler

    @app.on_event("shutdown")
    async def close_client() -> None:
        await client.aclose()

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"policy": scheduler.policy, "queue": scheduler.queue_depth, "active": scheduler.active_count}

    @app.post("/v1/completions")
    async def completions(request: Request) -> Response:
        received_ns = time.monotonic_ns()
        body = await request.body()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(400, "invalid JSON") from exc
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or payload.get("stream") is not True:
            raise HTTPException(400, "CacheFlow experiment requires a string prompt and stream=true")
        if payload.get("add_special_tokens") is not False:
            raise HTTPException(400, "set add_special_tokens=false for auditable token alignment")
        request_id = request.headers.get("x-cacheflow-request-id") or os.urandom(8).hex()
        run_id = request.headers.get("x-cacheflow-run-id") or "unlabeled"
        arrival_header = request.headers.get("x-cacheflow-arrival-ns")
        try:
            arrival_ns = int(arrival_header) if arrival_header else received_ns
            if arrival_ns > received_ns or received_ns - arrival_ns > 60_000_000_000:
                raise ValueError
        except ValueError:
            arrival_ns = received_ns
        token_ids = tokenizer.encode(prompt, add_special_tokens=False)
        blocks = prefix_blocks(token_ids, block_size=scheduler.block_size, namespace=model)
        # Only the declared request class (chat first) matters, and only under policy class_first.
        priority = 0 if request.headers.get("x-cacheflow-class") == "chat" else 1
        ticket: Ticket = await scheduler.admit(request_id, blocks, arrival_ns=arrival_ns, priority=priority)
        headers = {"content-type": "application/json"}
        stream_cm = client.stream("POST", upstream + "/v1/completions", content=body, headers=headers)
        try:
            upstream_response = await stream_cm.__aenter__()
        except Exception as exc:
            await scheduler.finish(ticket, cancellation_reason="upstream_connect_error")
            await trace.append(_record(ticket, received_ns, len(token_ids), run_id=run_id, status="upstream_connect_error"))
            raise HTTPException(502, f"upstream connection failed: {type(exc).__name__}") from exc
        if upstream_response.status_code >= 400:
            error_body = await upstream_response.aread()
            await stream_cm.__aexit__(None, None, None)
            await scheduler.finish(ticket, cancellation_reason="upstream_http_error")
            await trace.append(_record(ticket, received_ns, len(token_ids), run_id=run_id, status=f"upstream_http_{upstream_response.status_code}"))
            return Response(content=error_body, status_code=upstream_response.status_code, media_type="application/json")

        async def relay():
            buffer = bytearray()
            status = "ok"
            try:
                async for chunk in upstream_response.aiter_bytes():
                    if ticket.first_token_ns is None and _first_content_token(buffer, chunk):
                        await scheduler.mark_first_token(ticket)
                    yield chunk
            except asyncio.CancelledError:
                status = "client_cancelled"
                raise
            except Exception as exc:
                status = f"stream_error:{type(exc).__name__}"
                raise
            finally:
                await stream_cm.__aexit__(None, None, None)
                if ticket.first_token_ns is None and status == "ok":
                    status = "empty_response"
                await scheduler.finish(ticket, cancellation_reason=None if status == "ok" else status)
                await trace.append(_record(ticket, received_ns, len(token_ids), run_id=run_id, status=status))

        return StreamingResponse(relay(), media_type="text/event-stream", headers={"X-Cacheflow-Request-ID": request_id})

    return app


def _record(ticket: Ticket, received_ns: int, input_tokens: int, *, run_id: str, status: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "request_id": ticket.request_id,
        "arrival_ns": ticket.arrival_ns,
        "received_ns": received_ns,
        "enqueue_ns": ticket.enqueued_ns,
        "ingress_prepare_ms": (ticket.enqueued_ns - received_ns) / 1e6,
        "dispatch_ns": ticket.dispatch_ns,
        "admission_wait_ms": (ticket.dispatch_ns - ticket.enqueued_ns) / 1e6 if ticket.dispatch_ns else None,
        "admission_deadline_ns": ticket.deadline_ns,
        "admission_deadline_overrun_ms": max(0.0, (ticket.dispatch_ns - ticket.deadline_ns) / 1e6) if ticket.dispatch_ns else None,
        "first_token_ns": ticket.first_token_ns,
        "complete_ns": ticket.complete_ns,
        "queue_wait_ms": (ticket.dispatch_ns - ticket.arrival_ns) / 1e6 if ticket.dispatch_ns else None,
        "input_tokens": input_tokens,
        "prefix_group": ticket.group,
        "priority": ticket.priority,
        "promoted": ticket.promoted,
        "delay_hit_candidate": ticket.delay_hit_candidate,
        "readiness_guard_bypassed": ticket.readiness_guard_bypassed,
        "readiness_estimate_ms": ticket.readiness_estimate_ms,
        "recent_match": ticket.recent_match,
        "status": status,
    }


