"""Regenerate paired prompt/output-hash audit for the headline experiments."""
from __future__ import annotations

import json
from pathlib import Path

from cacheflow.quality import compare

PAIRS = [
    ("b2-revisit-8k-r1", "b3-revisit-8k-r1"),
    ("b2-revisit-8k-r2", "b3-revisit-8k-r2"),
    ("b2-distinct-2k-r1", "b3-distinct-2k-r1"),
    ("b2-distinct-2k-r2", "b3-distinct-2k-r2"),
    ("b2-revisit-8k-holdout-r6", "b3g-revisit-8k-holdout-r1"),
    ("b2-revisit-8k-holdout-r7", "b3g-revisit-8k-holdout-r2"),
    ("b1-cap4-8k-r1", "b2-cap4-8k-r1"),
    ("b1-cap4-8k-r2", "b2-cap4-8k-r2"),
    ("b1-cap8-8k-r1", "b2-cap8-8k-r1"),
    ("b1-cap8-8k-r2", "b2-cap8-8k-r2"),
    ("b1-ws12-cap8-r1", "b2-ws12-cap8-r1"),
    ("b1-ws12-cap8-r2", "b2-ws12-cap8-r2"),
    ("b1-cap4-8k-r1", "b1-cap4-8k-r2"),
    ("b2-cap4-8k-r1", "b2-cap4-8k-r2"),
    ("b1-cap8-8k-r1", "b1-cap8-8k-r2"),
    ("b2-cap8-8k-r1", "b2-cap8-8k-r2"),
    ("b1-ws12-cap8-r1", "b1-ws12-cap8-r2"),
    ("b2-ws12-cap8-r1", "b2-ws12-cap8-r2"),
]

root = Path(__file__).resolve().parents[1]
raw = root / "results" / "raw"
out = root / "results" / "quality_audit.jsonl"
with out.open("w") as stream:
    for a, b in PAIRS:
        result = compare(raw / f"{a}.jsonl", raw / f"{b}.jsonl")
        stream.write(json.dumps(result, sort_keys=True) + "\n")
print(out)
