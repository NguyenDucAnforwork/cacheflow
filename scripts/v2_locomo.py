"""Audit official LoCoMo lengths and generate reproducible V2 request traces."""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict
from pathlib import Path

from transformers import AutoTokenizer

from cacheflow.locomo import (
    PROMPT_VERSION, build_trace, context_prefix, load_locomo,
    question_prompt, source_sha256,
)


def percentile(values: list[int], pct: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def audit(source: Path, tokenizer, output_tokens: int) -> dict:
    conversations = load_locomo(source)
    per_sample = []
    all_lengths = []
    for conversation in conversations:
        prefix = context_prefix(conversation)
        prefix_tokens = tokenizer.encode(prefix, add_special_tokens=False)
        prompt_ids = [tokenizer.encode(question_prompt(prefix, question), add_special_tokens=False)
                      for question in conversation.questions]
        lengths = [len(ids) for ids in prompt_ids]
        all_lengths.extend(lengths)
        per_sample.append({
            "sample_id": conversation.sample_id,
            "sessions": len(conversation.sessions),
            "qa_count": len(conversation.questions),
            "qa_answerable": sum(question.answer is not None for question in conversation.questions),
            "qa_adversarial": sum(question.adversarial_answer is not None for question in conversation.questions),
            "qa_invalid_evidence": sum(not question.evidence_valid for question in conversation.questions),
            "full_context_prefix_tokens": len(prefix_tokens),
            "qa_exact_token_prefix": sum(ids[:len(prefix_tokens)] == prefix_tokens for ids in prompt_ids),
            "qa_input_min": min(lengths),
            "qa_input_median": statistics.median(lengths),
            "qa_input_max": max(lengths),
            "qa_fit_12288": sum(length + output_tokens <= 12288 for length in lengths),
            "qa_fit_32768": sum(length + output_tokens <= 32768 for length in lengths),
        })
    return {
        "source_sha256": source_sha256(source), "prompt_version": PROMPT_VERSION,
        "text_only_image_policy": "use released blip_caption; never fetch image URLs",
        "output_tokens_reserved": output_tokens,
        "conversations": len(conversations), "questions": len(all_lengths),
        "qa_input_tokens": {"p50": percentile(all_lengths, 50),
                            "p90": percentile(all_lengths, 90), "max": max(all_lengths)},
        "qa_fit_12288": sum(item["qa_fit_12288"] for item in per_sample),
        "qa_fit_32768": sum(item["qa_fit_32768"] for item in per_sample),
        "qa_exact_token_prefix": sum(item["qa_exact_token_prefix"] for item in per_sample),
        "per_sample": per_sample,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["audit", "trace"])
    parser.add_argument("--source", type=Path, default=Path("data/raw/locomo10.json"))
    parser.add_argument("--tokenizer-path", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-tokens", type=int, default=64)
    parser.add_argument("--protocol", choices=["p_qa", "p_session"], default="p_qa")
    parser.add_argument("--arrival", choices=["grouped", "interleaved", "low_reuse"], default="interleaved")
    parser.add_argument("--sample-ids", nargs="*")
    parser.add_argument("--max-model-len", type=int, default=12288)
    parser.add_argument("--max-questions-per-sample", type=int)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--qps", type=float, default=2.0)
    parser.add_argument("--session-gap-ms", type=int, default=1000)
    args = parser.parse_args()
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_path, local_files_only=True, trust_remote_code=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.command == "audit":
        report = audit(args.source, tokenizer, args.output_tokens)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps({key: report[key] for key in ("source_sha256", "questions", "qa_input_tokens",
                                                       "qa_fit_12288", "qa_fit_32768")}, sort_keys=True))
    else:
        rows, manifest = build_trace(
            load_locomo(args.source), tokenizer, protocol=args.protocol, arrival=args.arrival,
            sample_ids=tuple(args.sample_ids) if args.sample_ids else None,
            max_model_len=args.max_model_len, output_tokens=args.output_tokens,
            max_questions_per_sample=args.max_questions_per_sample,
            seed=args.seed, qps=args.qps, session_gap_ms=args.session_gap_ms,
        )
        manifest["source_sha256"] = source_sha256(args.source)
        with args.output.open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(asdict(row), sort_keys=True) + "\n")
        manifest_path = args.output.with_suffix(".manifest.json")
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"trace": str(args.output), **manifest}, sort_keys=True))


if __name__ == "__main__":
    main()
