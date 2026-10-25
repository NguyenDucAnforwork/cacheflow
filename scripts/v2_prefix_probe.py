"""Generate matched producer/follower traces for the E1 feasibility gate."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict
from pathlib import Path

from transformers import AutoTokenizer

from cacheflow.data import _document
from cacheflow.locomo import V2TraceRow, trace_digest


def build_probe(tokenizer, *, prefix_tokens: int, pairs: int, follower_offset_ms: int,
                output_tokens: int, seed: int) -> list[V2TraceRow]:
    if prefix_tokens <= 0 or pairs <= 0 or follower_offset_ms < 0 or output_tokens <= 0:
        raise ValueError("invalid E1 parameter")
    rng = random.Random(seed)
    rows: list[V2TraceRow] = []
    for index in range(pairs):
        document = _document(rng, tokenizer, prefix_tokens, f"v2-probe-{index}")
        prefix = document + "\nQuestion:\n"
        common_ids = tokenizer.encode(prefix, add_special_tokens=False)
        for follow, question in enumerate(("Summarize the opening section.",
                                           "Identify the central evidence.")):
            prompt = f"{prefix}{question}\nAnswer:"
            ids = tokenizer.encode(prompt, add_special_tokens=False)
            if ids[:len(common_ids)] != common_ids:
                raise ValueError("probe does not have an exact tokenized prefix")
            rows.append(V2TraceRow(
                request_id=f"probe-{index:02d}-{'follower' if follow else 'producer'}",
                offset_ms=follower_offset_ms if follow else 0,
                prompt=prompt, input_tokens=len(ids), max_tokens=output_tokens,
                group=f"probe-{index:02d}", sample_id=f"probe-{index:02d}",
                qa_index=follow, category=0, protocol="prefix_probe", checkpoint_session=None,
            ))
    return sorted(rows, key=lambda row: (row.offset_ms, row.request_id))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokenizer-path", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix-tokens", type=int, required=True)
    parser.add_argument("--pairs", type=int, default=1)
    parser.add_argument("--follower-offset-ms", type=int, required=True)
    parser.add_argument("--output-tokens", type=int, default=32)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_path, local_files_only=True,
                                              trust_remote_code=False)
    rows = build_probe(tokenizer, prefix_tokens=args.prefix_tokens, pairs=args.pairs,
                       follower_offset_ms=args.follower_offset_ms,
                       output_tokens=args.output_tokens, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(asdict(row), sort_keys=True) + "\n")
    manifest = {"protocol": "prefix_probe", "arrival": "paired_offset",
                "prefix_tokens_target": args.prefix_tokens, "pairs": args.pairs,
                "follower_offset_ms": args.follower_offset_ms,
                "output_tokens": args.output_tokens, "seed": args.seed,
                "trace_sha256": trace_digest(rows)}
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
