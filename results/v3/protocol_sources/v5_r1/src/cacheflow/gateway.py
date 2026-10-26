"""Streaming OpenAI completions proxy with auditable admission timing."""

from __future__ import annotations

import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from transformers import AutoTokenizer

from .prefix import prefix_blocks
from .scheduler import AdmissionScheduler, Ticket
from .v4_prepare import prepare


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
    from .v3_scheduler import BaselineScheduler, V3_POLICIES
    from .v3_residency import ResidencyIndex, ResidencySubscriber, engine_block_hashes
    from .v3_memory_scheduler import ResidencyScheduler, RESIDENCY_POLICIES, PURE_PACKING_POLICIES
    residency_config = settings.get('residency', {})
    residency = ResidencyIndex()
    subscriber = ResidencySubscriber(residency, residency_config.get('endpoint', 'tcp://127.0.0.1:5557')) if residency_config.get('enabled') else None
    scheduler_cls = BaselineScheduler if settings["scheduler"]["policy"] in V3_POLICIES else AdmissionScheduler
    if settings['scheduler']['policy'] in RESIDENCY_POLICIES:
        if subscriber is None and settings['scheduler']['policy'] not in PURE_PACKING_POLICIES:
            raise ValueError('residency policies require a real KV-event subscriber')
        scheduler = ResidencyScheduler(**settings['scheduler'], residency_index=residency,
            kv_capacity_tokens=residency_config['kv_capacity_tokens'],
            max_bypasses=residency_config.get('max_bypasses', 4))
    else:
        scheduler = scheduler_cls(**settings["scheduler"])
    trace = TraceWriter(os.environ.get("CACHEFLOW_TRACE", "/workspace/results/raw/gateway.jsonl"))
    upstream = settings.get("upstream", "http://127.0.0.1:8000").rstrip("/")
    # Fresh local connections avoid reusing sockets closed during long admission pauses.
    # No retries: a failed POST is always reported and invalidates the run.
    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=30, read=float(settings.get("http_read_timeout_s",600)), write=30, pool=30),
        limits=httpx.Limits(max_connections=128,
            max_keepalive_connections=settings.get('upstream_keepalive_connections',128)))
    app = FastAPI(title="CacheFlow Gateway")
    app.state.scheduler = scheduler
    # One worker keeps mutable tokenizer settings serialized, including when a
    # cancelled HTTP task leaves CPU work running. Stream I/O stays on the loop.
    prepare_pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='cacheflow-prepare') if settings.get('prepare_in_thread',False) else None

    @app.on_event('startup')
    async def start_subscriber() -> None:
        if subscriber:
            subscriber.start()

    @app.on_event("shutdown")
    async def close_client() -> None:
        if subscriber:
            await subscriber.close()
        await client.aclose()
        if prepare_pool:
            await asyncio.to_thread(prepare_pool.shutdown,wait=True,cancel_futures=True)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"policy": scheduler.policy, "queue": scheduler.queue_depth, "active": scheduler.active_count,
                'completed_history_requests': len(scheduler._recent),
                'upstream_read_timeout_s': client.timeout.read,
                'prepare_mode': 'thread' if prepare_pool else 'inline',
                'decision_stats': scheduler.decision_stats() if hasattr(scheduler, 'decision_stats') else None,
                'residency': subscriber.stats() if subscriber else None}

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
            if arrival_ns > received_ns or received_ns - arrival_ns > 3_600_000_000_000:
                raise ValueError
        except ValueError:
            arrival_ns = received_ns
        prepare_queued=time.monotonic_ns()
        work=partial(prepare,tokenizer,prompt,scheduler.block_size,model,
            bool(subscriber) or scheduler.policy in PURE_PACKING_POLICIES)
        if prepare_pool:
            token_ids,blocks,engine_blocks,preparation=await asyncio.get_running_loop().run_in_executor(prepare_pool,work)
        else:
            token_ids,blocks,engine_blocks,preparation=work()
        ticket: Ticket = await scheduler.admit(request_id, blocks, arrival_ns=arrival_ns,
            engine_blocks=engine_blocks, input_tokens=len(token_ids), output_budget=int(payload.get('max_tokens', 96)))
        if subscriber:
            ticket.predicted_gpu_tokens = residency.matched_tokens(engine_blocks) if residency.known else None
        ticket.tokenize_ms = preparation['tokenize_ms']
        ticket.prefix_hash_ms = preparation['prefix_hash_ms']
        ticket.prepare_cpu_ms = preparation['cpu_ms']
        ticket.prepare_queue_ms = (preparation['start_ns']-prepare_queued)/1e6
        headers = {"content-type": "application/json"}
        stream_cm = client.stream("POST", upstream + "/v1/completions", content=body, headers=headers)
        try:
            upstream_response = await stream_cm.__aenter__()
        except Exception as exc:
            ticket.upstream_error_type = type(exc).__name__
            ticket.upstream_error_detail = (repr(exc)+'; cause='+repr(exc.__cause__))[:500]
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
        "tokenize_ms": ticket.tokenize_ms,
        "prefix_hash_ms": ticket.prefix_hash_ms,
        "prepare_cpu_ms": ticket.prepare_cpu_ms,
        "prepare_queue_ms": ticket.prepare_queue_ms,
        "dispatch_ns": ticket.dispatch_ns,
        "admission_wait_ms": (ticket.dispatch_ns - ticket.enqueued_ns) / 1e6 if ticket.dispatch_ns else None,
        "admission_deadline_ns": ticket.deadline_ns,
        "admission_deadline_overrun_ms": max(0.0, (ticket.dispatch_ns - ticket.deadline_ns) / 1e6) if ticket.dispatch_ns else None,
        "first_token_ns": ticket.first_token_ns,
        "complete_ns": ticket.complete_ns,
        "queue_wait_ms": (ticket.dispatch_ns - ticket.arrival_ns) / 1e6 if ticket.dispatch_ns else None,
        "input_tokens": input_tokens,
        "prefix_group": ticket.group,
        "delay_hit_candidate": ticket.delay_hit_candidate,
        "readiness_guard_bypassed": ticket.readiness_guard_bypassed,
        "readiness_estimate_ms": ticket.readiness_estimate_ms,
        "recent_match": ticket.recent_match,
        'dispatch_reason': ticket.dispatch_reason,
        'predicted_gpu_tokens': ticket.predicted_gpu_tokens,
        'reserved_active_tokens': ticket.reserved_active_tokens,
        'upstream_error_type': ticket.upstream_error_type,
        'upstream_error_detail': ticket.upstream_error_detail,
        "status": status,
    }


