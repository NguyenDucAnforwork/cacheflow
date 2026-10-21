"""Deterministic synthetic traces with genuine tokenized prefix reuse."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from typing import Literal

from transformers import PreTrainedTokenizerBase

Workload = Literal["long_doc", "long_doc_revisit", "multi_turn", "distinct"]
WORDS = (
    "archive circuit lattice spectrum operator dataset retrieval scheduler cache transport "
    "profile latency epoch sequence artifact evidence memory bandwidth context query "
    "vector signal model system experiment baseline admission queue prefix document "
    "analysis token response worker device host buffer trace metric pipeline inference "
    "compute storage policy tensor benchmark sample history chapter clause example "
    "source result method question answer comparison fairness budget request engine "
).split()


@dataclass(frozen=True)
class TraceRow:
    request_id: str
    offset_ms: int
    prompt: str
    input_tokens: int
    max_tokens: int
    group: str


def _document(rng: random.Random, tokenizer: PreTrainedTokenizerBase, target_tokens: int, label: str) -> str:
    parts = [f"Document {label}. This is a synthetic technical report with distinct facts.\n"]
    next_index = 0
    while True:
        batch = []
        for _ in range(30):
            words = " ".join(rng.choice(WORDS) for _ in range(22))
            batch.append(f"Section {next_index}: {words}. Fact code {label}-{next_index}.\n")
            next_index += 1
        parts.extend(batch)
        text = "".join(parts)
        token_ids = tokenizer.encode(text, add_special_tokens=False)
        if len(token_ids) >= target_tokens:
            return tokenizer.decode(token_ids[:target_tokens], clean_up_tokenization_spaces=False)


def build_trace(
    tokenizer: PreTrainedTokenizerBase,
    *,
    workload: Workload,
    seed: int = 7,
    target_input_tokens: int = 4096,
    groups: int = 8,
    per_group: int = 4,
    output_tokens: int = 64,
) -> list[TraceRow]:
    if workload not in ("long_doc", "long_doc_revisit", "multi_turn", "distinct"):
        raise ValueError(workload)
    rng = random.Random(seed)
    rows: list[TraceRow] = []
    if workload == "distinct":
        for i in range(groups * per_group):
            doc = _document(rng, tokenizer, target_input_tokens, f"distinct-{i}")
            prompt = doc + f"\nQuestion: Summarize the evidence for item {i}.\nAnswer:"
            rows.append(TraceRow(f"distinct-{i:03d}", i * 50, prompt,
                                 len(tokenizer.encode(prompt, add_special_tokens=False)), output_tokens, f"distinct-{i}"))
    elif workload in ("long_doc", "long_doc_revisit"):
        for group in range(groups):
            doc = _document(rng, tokenizer, target_input_tokens, f"doc-{group}")
            for question in range(per_group):
                prompt = doc + f"\nQuestion {question}: Which facts in this document relate to section {question * 7}?\nAnswer:"
                offset = group * 450 + question * 35
                if workload == "long_doc_revisit" and question == per_group - 1:
                    offset = groups * 450 + 4500 + group * 200
                rows.append(TraceRow(f"doc-{group:02d}-q{question}", offset,
                                     prompt, len(tokenizer.encode(prompt, add_special_tokens=False)),
                                     output_tokens, f"doc-{group}"))
    else:
        for group in range(groups):
            history = _document(rng, tokenizer, target_input_tokens, f"session-{group}")
            for turn in range(per_group):
                prompt = history + f"\nUser turn {turn}: Explain the last observation.\nAssistant:"
                rows.append(TraceRow(f"session-{group:02d}-t{turn}", group * 160 + turn * 600,
                                     prompt, len(tokenizer.encode(prompt, add_special_tokens=False)),
                                     output_tokens, f"session-{group}"))
                history += f"\nAssistant turn {turn}: The observation concerns cache locality and timing.\n"
    return sorted(rows, key=lambda row: (row.offset_ms, row.request_id))


def trace_digest(rows: list[TraceRow]) -> str:
    payload = json.dumps([asdict(row) for row in rows], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
