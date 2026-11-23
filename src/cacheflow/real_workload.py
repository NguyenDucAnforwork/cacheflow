"""Real-data replay traces: QuALITY documents/questions + ShareGPT chat prompts.

Dataset CONTENT is real (QuALITY v1.0.1 htmlstripped dev; ShareGPT_V3 unfiltered first human turns).
Request ARRIVAL TIMES are SIMULATED (fixed-seed schedules below); they are not taken from any dataset.
Prompt text is written only to the git-ignored data/ directory; the committed manifest has IDs, hashes and stats.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

from transformers import AutoTokenizer

from .data import trace_digest

QUALITY_URL = "https://github.com/nyu-mll/quality/raw/main/data/v1.0.1/QuALITY.v1.0.1.zip"
QUALITY_MEMBER = "QuALITY.v1.0.1.htmlstripped.dev"
SHAREGPT_REPO = "anon8231489123/ShareGPT_Vicuna_unfiltered"
SHAREGPT_FILE = "ShareGPT_V3_unfiltered_cleaned_split.json"
DOC_MAX_TOKENS = 48
CHAT_MAX_TOKENS = 96
INSTRUCTION = ("Read the article and answer the multiple-choice question about it. "
               "Answer with the letter of the correct option, then one short sentence of justification.")
# Simulated arrival profiles (ms). first_gap: spacing of first visits; q1_delay: second question after first visit;
# revisit_gap: spacing of late revisits that begin revisit_start after the last second question.
PROFILES = {
    "moderate": {"first_gap": 2000, "q1_delay": 3000, "revisit_start": 4000, "revisit_gap": 1500},
    "medium": {"first_gap": 900, "q1_delay": 2000, "revisit_start": 2500, "revisit_gap": 700},
    "mid65": {"first_gap": 650, "q1_delay": 1600, "revisit_start": 2000, "revisit_gap": 500},
    "mid50": {"first_gap": 500, "q1_delay": 1400, "revisit_start": 1750, "revisit_gap": 400},
    "burst": {"first_gap": 400, "q1_delay": 1200, "revisit_start": 1500, "revisit_gap": 300},
}
BLOCKLIST = ("sex", "porn", "nude", "naked", "fuck", "suicide", "kill", "rape", "nsfw", "erotic", "cock", "pussy")


@dataclass(frozen=True)
class RealRow:
    request_id: str
    offset_ms: int
    prompt: str
    input_tokens: int
    max_tokens: int
    group: str
    cls: str  # "doc" or "chat"
    gold_letter: str  # doc only; "" for chat
    source_id: str  # QuALITY question_unique_id or ShareGPT conversation id


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_quality(raw_dir: Path) -> tuple[Path, str]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    archive = raw_dir / "QuALITY.v1.0.1.zip"
    if not archive.exists():
        urllib.request.urlretrieve(QUALITY_URL, archive)  # noqa: S310 - fixed https GitHub URL
    member = raw_dir / QUALITY_MEMBER
    if not member.exists():
        with zipfile.ZipFile(archive) as zf:
            member.write_bytes(zf.read(QUALITY_MEMBER))
    return member, sha256_file(archive)


def fetch_sharegpt(raw_dir: Path) -> tuple[Path, str]:
    from huggingface_hub import hf_hub_download

    path = Path(hf_hub_download(SHAREGPT_REPO, SHAREGPT_FILE, repo_type="dataset", cache_dir=str(raw_dir / "hf")))
    return path, path.parent.name  # snapshot directory name is the dataset commit hash


def _render(tokenizer, content: str) -> str:
    return tokenizer.apply_chat_template([{"role": "user", "content": content}], tokenize=False,
                                         add_generation_prompt=True, enable_thinking=False)


def _doc_prompt(tokenizer, article: str, question: dict) -> str:
    options = "\n".join(f"{letter}. {text}" for letter, text in zip("ABCD", question["options"]))
    content = f"{INSTRUCTION}\n\nArticle:\n{article}\n\nQuestion: {question['question']}\n\n{options}"
    return _render(tokenizer, content)


def _common_prefix(a: list[int], b: list[int]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _dist(values: list[int]) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {}
    pick = lambda p: ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * p)))]  # noqa: E731
    return {"n": len(ordered), "min": ordered[0], "p50": pick(0.5), "p95": pick(0.95), "max": ordered[-1],
            "mean": round(statistics.mean(ordered), 1), "sum": sum(ordered)}


def select_content(tokenizer, quality_path: Path, sharegpt_path: Path, *, seed: int, docs: int, chats: int,
                   min_doc_tokens: int, max_doc_tokens: int) -> dict:
    rng = random.Random(seed)
    articles = [json.loads(line) for line in quality_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    labels = [q["gold_label"] for a in articles for q in a["questions"]]
    assert min(labels) == 1 and max(labels) == 4, "QuALITY gold_label is expected to be 1-indexed"
    eligible = []
    for article in articles:
        count = len(tokenizer.encode(article["article"], add_special_tokens=False))
        if min_doc_tokens <= count <= max_doc_tokens and len(article["questions"]) >= 3:
            eligible.append((article["article_id"], count, article))
    eligible.sort(key=lambda item: item[0])
    chosen_docs = rng.sample(eligible, docs)
    doc_items = []
    for article_id, count, article in chosen_docs:
        picks = rng.sample(article["questions"], 3)
        doc_items.append({"article_id": article_id, "article_tokens": count, "article": article["article"],
                          "title": article["title"], "questions": picks})
    conversations = json.loads(sharegpt_path.read_text(encoding="utf-8"))
    pool = []
    for conv in conversations:
        turns = conv.get("conversations") or []
        if not turns or turns[0].get("from") != "human":
            continue
        text = (turns[0].get("value") or "").strip()
        if not (30 <= len(text) <= 600) or text.count("\n") > 3 or "```" in text:
            continue
        if sum(ch.isascii() for ch in text) / len(text) < 0.99 or any(w in text.lower() for w in BLOCKLIST):
            continue
        pool.append((str(conv["id"]), text))
    pool.sort(key=lambda item: item[0])
    rng.shuffle(pool)
    chat_items = []
    for conv_id, text in pool:
        if len(chat_items) == chats:
            break
        tokens = len(tokenizer.encode(text, add_special_tokens=False))
        if 8 <= tokens <= 120:
            chat_items.append({"id": conv_id, "text": text, "tokens": tokens})
    return {"docs": doc_items, "chats": chat_items, "pool_size": len(pool), "eligible_docs": len(eligible),
            "sharegpt_conversations": len(conversations)}


def build_rows(tokenizer, content: dict, profile: str, seed: int) -> tuple[list[RealRow], dict]:
    params = PROFILES[profile]
    rng = random.Random(seed + 1000)
    rows: list[RealRow] = []
    doc_stats = []
    n_docs = len(content["docs"])
    last_q1 = (n_docs - 1) * params["first_gap"] + params["q1_delay"]
    revisit0 = last_q1 + params["revisit_start"]
    for g, doc in enumerate(content["docs"]):
        offsets = (g * params["first_gap"], g * params["first_gap"] + params["q1_delay"], revisit0 + g * params["revisit_gap"])
        ids = []
        for q, (question, offset) in enumerate(zip(doc["questions"], offsets)):
            prompt = _doc_prompt(tokenizer, doc["article"], question)
            token_ids = tokenizer.encode(prompt, add_special_tokens=False)
            ids.append(token_ids)
            rows.append(RealRow(f"doc-{g:02d}-q{q}", offset, prompt, len(token_ids), DOC_MAX_TOKENS, f"doc-{g:02d}", "doc",
                                "ABCD"[question["gold_label"] - 1], question["question_unique_id"]))
        doc_stats.append({"group": f"doc-{g:02d}", "article_id": doc["article_id"], "prompt_tokens": [len(i) for i in ids],
                          "shared_prefix_tokens_q0_q1": _common_prefix(ids[0], ids[1]),
                          "shared_prefix_tokens_q0_q2": _common_prefix(ids[0], ids[2])})
    span = max(row.offset_ms for row in rows)
    for i, chat in enumerate(content["chats"]):
        offset = int((i + rng.uniform(0.1, 0.9)) * span / len(content["chats"]))
        prompt = _render(tokenizer, chat["text"])
        token_ids = tokenizer.encode(prompt, add_special_tokens=False)
        rows.append(RealRow(f"chat-{i:02d}", offset, prompt, len(token_ids), CHAT_MAX_TOKENS, f"chat-{i:02d}", "chat", "", chat["id"]))
    rows.sort(key=lambda row: (row.offset_ms, row.request_id))
    return rows, {"docs": doc_stats, "span_ms": span, "revisit_start_ms": revisit0, "profile": {"name": profile, **params}}


def write_trace(path: Path, rows: list[RealRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(asdict(row), sort_keys=True) + "\n")


def load_trace(path: str | Path) -> tuple[list[RealRow], str]:
    rows = [RealRow(**json.loads(line)) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows, trace_digest(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download QuALITY/ShareGPT and materialize deterministic real-data traces")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--raw-dir", default="/workspace/data/raw")
    parser.add_argument("--trace-dir", default="/workspace/data/traces")
    parser.add_argument("--manifest-dir", default="/workspace/results/real")
    parser.add_argument("--prefix", default="real", help="trace/manifest file prefix")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--docs", type=int, default=14)
    parser.add_argument("--chats", type=int, default=20)
    parser.add_argument("--min-doc-tokens", type=int, default=5500)
    parser.add_argument("--max-doc-tokens", type=int, default=8400)
    args = parser.parse_args()
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True, trust_remote_code=False)
    raw = Path(args.raw_dir)
    quality_path, quality_zip_sha = fetch_quality(raw)
    sharegpt_path, sharegpt_rev = fetch_sharegpt(raw)
    content = select_content(tokenizer, quality_path, sharegpt_path, seed=args.seed, docs=args.docs, chats=args.chats,
                             min_doc_tokens=args.min_doc_tokens, max_doc_tokens=args.max_doc_tokens)
    provenance = {
        "quality": {"source": QUALITY_URL, "member": QUALITY_MEMBER, "zip_sha256": quality_zip_sha,
                    "dev_member_sha256": sha256_file(quality_path), "license_note": "QuALITY: see upstream repo; article text not committed"},
        "sharegpt": {"repo": SHAREGPT_REPO, "file": SHAREGPT_FILE, "dataset_revision": sharegpt_rev,
                     "file_sha256": sha256_file(sharegpt_path), "conversations": content["sharegpt_conversations"],
                     "filters": "first human turn; 30-600 chars; <=3 newlines; no code fence; >=99% ASCII; keyword blocklist; 8-120 tokens; fixed-seed sample"},
        "selection": {"seed": args.seed, "eligible_docs_in_token_range": content["eligible_docs"], "chat_pool_size": content["pool_size"],
                      "doc_token_range": [args.min_doc_tokens, args.max_doc_tokens]},
        "arrival_times": "SIMULATED fixed-seed schedules (not from the datasets); real content only",
    }
    for profile in PROFILES:
        rows, extra = build_rows(tokenizer, content, profile, args.seed)
        trace_path = Path(args.trace_dir) / f"{args.prefix}_{profile}.jsonl"
        write_trace(trace_path, rows)
        _, digest = load_trace(trace_path)
        by_cls = {cls: [r for r in rows if r.cls == cls] for cls in ("doc", "chat")}
        doc_prompt_sizes = [d["prompt_tokens"][0] for d in extra["docs"]]
        manifest = {
            "trace": f"{args.prefix}_{profile}", "trace_sha256": digest, "requests": len(rows), "provenance": provenance, **extra,
            "request_counts": {k: len(v) for k, v in by_cls.items()},
            "prompt_token_distribution": {k: _dist([r.input_tokens for r in v]) for k, v in by_cls.items()},
            "doc_unique_prefix_tokens_sum": sum(doc_prompt_sizes),
            "shared_prefix_tokens": _dist([d["shared_prefix_tokens_q0_q1"] for d in extra["docs"]] + [d["shared_prefix_tokens_q0_q2"] for d in extra["docs"]]),
            "output_token_budget": {"doc": DOC_MAX_TOKENS, "chat": CHAT_MAX_TOKENS},
            "requests_table": [{"request_id": r.request_id, "offset_ms": r.offset_ms, "cls": r.cls, "input_tokens": r.input_tokens,
                                "max_tokens": r.max_tokens, "prompt_sha256": hashlib.sha256(r.prompt.encode()).hexdigest(),
                                "source_id": r.source_id, "gold_letter": r.gold_letter} for r in rows],
        }
        out = Path(args.manifest_dir) / f"{args.prefix}_{profile}.manifest.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
        print(profile, digest, len(rows), "doc prompt tokens", _dist([r.input_tokens for r in by_cls["doc"]]),
              "unique doc working set tokens", sum(doc_prompt_sizes))


if __name__ == "__main__":
    main()
