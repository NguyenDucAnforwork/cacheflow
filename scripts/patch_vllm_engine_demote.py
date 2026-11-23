"""Idempotent patch of vLLM 0.22.0: deadline-aware demotion order inside the priority waiting queue (see docs/engine_demote_prereg.md).

Adds DemotingPriorityRequestQueue to vllm/v1/core/sched/request_queue.py, used only when the environment variable CACHEFLOW_ENGINE_DEMOTE=1
(otherwise create_request_queue returns vLLM's unmodified queue). Usage: python scripts/patch_vllm_engine_demote.py [--check] [--force]  (--force re-applies from the .orig backup).
Optional per-request decision log: set CACHEFLOW_ENGINE_DEMOTE_LOG to a file path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MARK = "CACHEFLOW_ENGINE_DEMOTE"

CLASS = '''

class DemotingPriorityRequestQueue(PriorityRequestQueue):
    """Priority queue with a deadline-aware demotion tier (CacheFlow experiment, enabled by CACHEFLOW_ENGINE_DEMOTE=1).

    Next request = min over (tier, priority, arrival_time): tier 0 for requests with priority 0 (chat), tier 1 for other requests (documents)
    that can still meet a 3 s TTFT SLO, tier 2 for documents already doomed: (now - arrival_time) + 72 ms per 1,000 prompt tokens > 3 s.
    Doomed documents are still served, after everything else. The choice made by peek_request is the one pop_request removes."""

    SLO_S = 3.0
    MS_PER_1K_TOKENS = 72.0

    def __init__(self) -> None:
        super().__init__()
        self._peeked = None

    def _key(self, request: Request, now: float):
        if request.priority == 0:
            tier = 0
        else:
            service_s = request.num_prompt_tokens / 1000.0 * self.MS_PER_1K_TOKENS / 1000.0
            tier = 2 if (now - request.arrival_time) + service_s > self.SLO_S else 1
        return (tier, request.priority, request.arrival_time)

    def _best(self) -> Request:
        now = time.time()
        return min(self._heap, key=lambda r: self._key(r, now))

    def add_request(self, request: Request) -> None:
        self._peeked = None
        super().add_request(request)

    def peek_request(self) -> Request:
        if not self._heap:
            raise IndexError("peek from empty heap")
        self._peeked = self._best()
        return self._peeked

    def _log(self, request: Request) -> None:
        path = os.environ.get("CACHEFLOW_ENGINE_DEMOTE_LOG")
        if not path or getattr(request, "_cf_logged", False):
            return
        request._cf_logged = True
        now = time.time()
        tier, priority, arrival = self._key(request, now)
        service_s = request.num_prompt_tokens / 1000.0 * self.MS_PER_1K_TOKENS / 1000.0
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps({"t": now, "arrival": arrival, "tokens": request.num_prompt_tokens, "priority": priority, "tier": tier,
                                   "waited_s": now - arrival, "est_service_s": service_s}) + "\\n")

    def pop_request(self) -> Request:
        if not self._heap:
            raise IndexError("pop from empty heap")
        request = self._peeked if (self._peeked is not None and self._peeked in self._heap) else self._best()
        self._log(request)  # optional per-request trace of the decision (first pop only)
        self._peeked = None
        self._heap.remove(request)
        heapq.heapify(self._heap)
        return request

    def __iter__(self):
        now = time.time()
        yield from sorted(self._heap, key=lambda r: self._key(r, now))

'''


def locate() -> Path:
    spec = importlib.util.find_spec("vllm")
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit("vllm not importable")
    return Path(list(spec.submodule_search_locations)[0]) / "v1" / "core" / "sched" / "request_queue.py"


def main() -> None:
    path = locate()
    text = path.read_text(encoding="utf-8")
    if "--force" in sys.argv:  # re-apply from the pristine backup
        backup_path = path.with_suffix(".py.orig")
        if backup_path.exists():
            text = backup_path.read_text(encoding="utf-8")
    elif MARK in text:
        print("already patched:", path)
        return
    if "--check" in sys.argv:
        print("not patched:", path)
        return
    backup = path.with_suffix(".py.orig")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
    for module in ("json", "os", "time"):
        if f"import {module}\n" not in text:
            text = text.replace("import heapq\n", f"import heapq\nimport {module}\n", 1)
    anchor = "def create_request_queue(policy: SchedulingPolicy) -> RequestQueue:"
    assert anchor in text
    text = text.replace(anchor, CLASS.lstrip("\n") + "\n" + anchor, 1)
    old = "    if policy == SchedulingPolicy.PRIORITY:\n        return PriorityRequestQueue()"
    assert old in text
    text = text.replace(old, '    if policy == SchedulingPolicy.PRIORITY:\n        if os.environ.get("CACHEFLOW_ENGINE_DEMOTE") == "1":\n            return DemotingPriorityRequestQueue()\n        return PriorityRequestQueue()', 1)
    path.write_text(text, encoding="utf-8")
    print("patched:", path, "(backup", backup.name + ")")


if __name__ == "__main__":
    main()
