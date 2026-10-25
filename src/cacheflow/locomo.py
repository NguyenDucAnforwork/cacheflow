"""Deterministic text-only LoCoMo adapters for CacheFlow V2.

The official source JSON is kept outside Git.  Neither gold answers nor evidence
labels are inserted into prompts; they remain available only for evaluation.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Protocol


class Tokenizer(Protocol):
    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]: ...


@dataclass(frozen=True)
class Turn:
    speaker: str
    dia_id: str
    text: str
    caption: str | None


@dataclass(frozen=True)
class Session:
    number: int
    date_time: str
    turns: tuple[Turn, ...]


@dataclass(frozen=True)
class Question:
    index: int
    text: str
    answer: str | None
    adversarial_answer: str | None
    category: int
    evidence: tuple[str, ...]
    evidence_raw: tuple[str, ...]
    evidence_valid: bool


@dataclass(frozen=True)
class Conversation:
    sample_id: str
    speaker_a: str
    speaker_b: str
    sessions: tuple[Session, ...]
    questions: tuple[Question, ...]


@dataclass(frozen=True)
class V2TraceRow:
    request_id: str
    offset_ms: int
    prompt: str
    input_tokens: int
    max_tokens: int
    group: str
    sample_id: str
    qa_index: int
    category: int
    protocol: Literal["p_qa", "p_session", "prefix_probe"]
    checkpoint_session: int | None


_SESSION = re.compile(r"session_(\d+)$")
_DIALOG = re.compile(r"D(\d+):(\d+)$")
PROMPT_VERSION = "locomo-text-v1"


def source_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_locomo(path: str | Path) -> tuple[Conversation, ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("LoCoMo source must be a nonempty list")
    result: list[Conversation] = []
    seen_samples: set[str] = set()
    for item in raw:
        sample_id = item["sample_id"]
        if sample_id in seen_samples:
            raise ValueError(f"duplicate sample_id: {sample_id}")
        seen_samples.add(sample_id)
        source = item["conversation"]
        numbers = sorted(int(match.group(1)) for key in source if (match := _SESSION.fullmatch(key)))
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError(f"nonconsecutive sessions: {sample_id}")
        sessions: list[Session] = []
        seen_dialogs: set[str] = set()
        for number in numbers:
            turns: list[Turn] = []
            for turn in source[f"session_{number}"]:
                dia_id = turn["dia_id"]
                match = _DIALOG.fullmatch(dia_id)
                if not match or int(match.group(1)) != number or dia_id in seen_dialogs:
                    raise ValueError(f"invalid or duplicate dialog ID: {sample_id}/{dia_id}")
                seen_dialogs.add(dia_id)
                caption = turn.get("blip_caption")
                turns.append(Turn(turn["speaker"], dia_id, turn["text"], caption or None))
            sessions.append(Session(number, source[f"session_{number}_date_time"], tuple(turns)))
        questions: list[Question] = []
        for index, qa in enumerate(item["qa"]):
            evidence_raw = tuple(qa["evidence"])
            # The release has a few cells containing multiple IDs in one string
            # and a few malformed IDs. Preserve the source while marking these
            # unusable for checkpoint scheduling rather than guessing a repair.
            evidence = tuple(dialog for cell in evidence_raw for dialog in re.findall(r"D\d+:\d+", cell))
            evidence_valid = bool(evidence) and all(dialog in seen_dialogs for dialog in evidence)
            if any(re.sub(r"D\d+:\d+", "", cell).strip(" ;,") for cell in evidence_raw):
                evidence_valid = False
            answer = qa.get("answer")
            questions.append(Question(index, qa["question"], None if answer is None else str(answer),
                                      qa.get("adversarial_answer"), int(qa["category"]), evidence,
                                      evidence_raw, evidence_valid))
        result.append(Conversation(sample_id, source["speaker_a"], source["speaker_b"],
                                   tuple(sessions), tuple(questions)))
    return tuple(result)


def context_prefix(conversation: Conversation, *, through_session: int | None = None) -> str:
    """Render a stable shared prefix. Image URLs and hidden summaries are excluded."""
    sessions = conversation.sessions if through_session is None else tuple(
        session for session in conversation.sessions if session.number <= through_session
    )
    parts = [f"Conversation between {conversation.speaker_a} and {conversation.speaker_b}.\n"]
    for session in sessions:
        parts.append(f"\nSession {session.number} ({session.date_time}):\n")
        for turn in session.turns:
            parts.append(f"[{turn.dia_id}] {turn.speaker}: {turn.text}\n")
            if turn.caption:
                parts.append(f"[{turn.dia_id} image caption] {turn.caption}\n")
    parts.append("\nAnswer the question using only the conversation above. If the answer is not stated, say 'I don't know'.\nQuestion:\n")
    return "".join(parts)


def question_prompt(prefix: str, question: Question) -> str:
    return f"{prefix}{question.text}\nAnswer:"


def evidence_checkpoint(question: Question) -> int | None:
    if not question.evidence_valid:
        return None
    return max(int(_DIALOG.fullmatch(dialog).group(1)) for dialog in question.evidence)


def trace_digest(rows: list[V2TraceRow]) -> str:
    payload = json.dumps([asdict(row) for row in rows], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def build_trace(
    conversations: tuple[Conversation, ...], tokenizer: Tokenizer, *,
    protocol: Literal["p_qa", "p_session"] = "p_qa",
    arrival: Literal["grouped", "interleaved", "low_reuse"] = "interleaved",
    sample_ids: tuple[str, ...] | None = None,
    max_model_len: int = 12288,
    output_tokens: int = 64,
    max_questions_per_sample: int | None = None,
    seed: int = 7,
    qps: float = 2.0,
    session_gap_ms: int = 1000,
) -> tuple[list[V2TraceRow], dict[str, Any]]:
    """Build a fit-filtered trace with seeded open-loop arrivals.

    Low-reuse selects at most one question per conversation. This is a control,
    not a production workload. The original QA text and context are unchanged.
    """
    if protocol not in ("p_qa", "p_session") or arrival not in ("grouped", "interleaved", "low_reuse"):
        raise ValueError("invalid protocol or arrival")
    if qps <= 0 or max_model_len <= output_tokens or output_tokens <= 0 or session_gap_ms < 0:
        raise ValueError("invalid QPS or token budget")
    selected = [conversation for conversation in conversations
                if sample_ids is None or conversation.sample_id in sample_ids]
    if sample_ids is not None and set(sample_ids) != {conversation.sample_id for conversation in selected}:
        raise ValueError("unknown sample ID")
    by_sample: dict[str, list[V2TraceRow]] = {}
    excluded = {"no_evidence": 0, "context_too_long": 0}
    for conversation in selected:
        candidates: list[V2TraceRow] = []
        questions = conversation.questions
        if max_questions_per_sample is not None:
            questions = questions[:max_questions_per_sample]
        prefix = context_prefix(conversation) if protocol == "p_qa" else None
        prefix_ids = tokenizer.encode(prefix, add_special_tokens=False) if prefix is not None else None
        for question in questions:
            checkpoint = None if protocol == "p_qa" else evidence_checkpoint(question)
            if protocol == "p_session" and checkpoint is None:
                excluded["no_evidence"] += 1
                continue
            actual_prefix = prefix if prefix is not None else context_prefix(conversation, through_session=checkpoint)
            prompt = question_prompt(actual_prefix, question)
            prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)
            if prefix_ids is not None and prompt_ids[:len(prefix_ids)] != prefix_ids:
                raise ValueError(f"tokenized prefix changed: {conversation.sample_id}/q{question.index}")
            count = len(prompt_ids)
            if count + output_tokens > max_model_len:
                excluded["context_too_long"] += 1
                continue
            candidates.append(V2TraceRow(
                request_id=f"{conversation.sample_id}-q{question.index:03d}", offset_ms=0,
                prompt=prompt, input_tokens=count, max_tokens=output_tokens,
                group=conversation.sample_id, sample_id=conversation.sample_id,
                qa_index=question.index, category=question.category, protocol=protocol,
                checkpoint_session=checkpoint,
            ))
        if protocol == "p_session":
            candidates.sort(key=lambda row: (row.checkpoint_session, row.qa_index))
        by_sample[conversation.sample_id] = candidates[:1] if arrival == "low_reuse" else candidates
    ordered: list[V2TraceRow] = []
    if arrival in ("grouped", "low_reuse"):
        ordered = [row for sample in selected for row in by_sample[sample.sample_id]]
    else:
        depth = max((len(rows) for rows in by_sample.values()), default=0)
        ordered = [by_sample[sample.sample_id][index] for index in range(depth)
                   for sample in selected if index < len(by_sample[sample.sample_id])]
    rng = random.Random(seed)
    current_ms = 0.0
    rows: list[V2TraceRow] = []
    last_checkpoint: dict[str, int] = {}
    for row in ordered:
        if protocol == "p_session" and row.sample_id in last_checkpoint and row.checkpoint_session != last_checkpoint[row.sample_id]:
            current_ms += session_gap_ms
        current_ms += rng.expovariate(qps) * 1000
        rows.append(V2TraceRow(**{**asdict(row), "offset_ms": round(current_ms)}))
        if protocol == "p_session":
            last_checkpoint[row.sample_id] = row.checkpoint_session
    return rows, {"selected_samples": [sample.sample_id for sample in selected],
                  "excluded": excluded, "requests": len(rows), "trace_sha256": trace_digest(rows),
                  "protocol": protocol, "arrival": arrival, "seed": seed, "qps": qps,
                  "max_model_len": max_model_len, "output_tokens": output_tokens,
                  "session_gap_ms": session_gap_ms if protocol == "p_session" else None,
                  "prompt_version": PROMPT_VERSION}
