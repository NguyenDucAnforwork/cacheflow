"""Small localhost OTLP gRPC sink for one non-comparative LMCache profiling run."""

from __future__ import annotations

import argparse
import json
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import grpc
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2, metrics_service_pb2_grpc
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc


class Sink(trace_service_pb2_grpc.TraceServiceServicer,
           metrics_service_pb2_grpc.MetricsServiceServicer):
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("w", encoding="utf-8")
        self.lock = threading.Lock()
        self.trace_batches = 0
        self.spans = 0

    def Export(self, request, context):  # type: ignore[override]
        if hasattr(request, "resource_spans"):
            records = []
            for resource in request.resource_spans:
                for scope in resource.scope_spans:
                    for span in scope.spans:
                        records.append({
                            "name": span.name,
                            "trace_id": span.trace_id.hex(),
                            "span_id": span.span_id.hex(),
                            "parent_span_id": span.parent_span_id.hex(),
                            "start_time_unix_nano": span.start_time_unix_nano,
                            "end_time_unix_nano": span.end_time_unix_nano,
                            "attributes": {attribute.key: MessageToDict(attribute.value)
                                           for attribute in span.attributes},
                        })
            with self.lock:
                for record in records:
                    self.file.write(json.dumps(record, separators=(",", ":")) + "\n")
                self.file.flush()
                self.trace_batches += 1
                self.spans += len(records)
            return trace_service_pb2.ExportTraceServiceResponse()
        return metrics_service_pb2.ExportMetricsServiceResponse()

    def close(self) -> None:
        with self.lock:
            self.file.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=4317)
    args = parser.parse_args()
    sink = Sink(args.output)
    server = grpc.server(ThreadPoolExecutor(max_workers=4))
    trace_service_pb2_grpc.add_TraceServiceServicer_to_server(sink, server)
    metrics_service_pb2_grpc.add_MetricsServiceServicer_to_server(sink, server)
    server.add_insecure_port(f"127.0.0.1:{args.port}")
    done = threading.Event()

    def stop(_signum, _frame):
        done.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server.start()
    print(f"OTLP sink listening on 127.0.0.1:{args.port}", flush=True)
    done.wait()
    server.stop(grace=5).wait()
    sink.close()
    print(f"Captured {sink.spans} spans in {sink.trace_batches} batches", flush=True)


if __name__ == "__main__":
    main()
