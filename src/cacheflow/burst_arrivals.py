"""Re-time an existing real-content trace with real arrival structure from BurstGPT (Azure OpenAI GPT service trace).

BurstGPT has timestamps (integer seconds), request/response token counts and a log type, but no text. This builder keeps the
document and chat *content* of a source trace and takes the *arrival process* of the 74 independent arrivals (60 chats + 14
first document visits) from a window of consecutive 'Conversation log' rows: timestamps get a seeded uniform jitter inside their
second, the window is rescaled to `--span-ms`, and the 14 requests with the largest `Request tokens` in the window become the
document first visits (length rank decides the class; an arbitrary but fixed rule). Second and third document visits keep a
fixed offset after the first (`--q1-delay`, `--q2-delay`).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
from dataclasses import replace
from pathlib import Path

from .real_workload import load_trace, write_trace


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="/workspace/data/raw/burstgpt/BurstGPT_1.csv")
    parser.add_argument("--src-trace", default="/workspace/data/traces/real60_mid45.jsonl")
    parser.add_argument("--trace-dir", default="/workspace/data/traces")
    parser.add_argument("--manifest-dir", default="/workspace/results/real")
    parser.add_argument("--prefix", default="bg")
    parser.add_argument("--windows", type=int, nargs="+", default=[1, 2], help="window seeds; each makes trace <prefix>_w<seed>")
    parser.add_argument("--span-ms", type=int, default=10000)
    parser.add_argument("--q1-delay", type=int, default=1300)
    parser.add_argument("--q2-delay", type=int, default=8000)
    args = parser.parse_args()
    rows, _ = load_trace(args.src_trace)
    docs = {}
    chats = []
    for row in rows:
        if row.cls == "doc":
            docs.setdefault(row.group, {})[row.request_id[-2:]] = row
        else:
            chats.append(row)
    chats.sort(key=lambda r: r.request_id)
    groups = sorted(docs)
    n_arrivals = len(chats) + len(groups)
    stamps, tokens = [], []
    with Path(args.csv).open(newline="") as file:
        for rec in csv.DictReader(file):
            if rec["Log Type"] == "Conversation log" and float(rec["Request tokens"]) > 0:
                stamps.append(float(rec["Timestamp"]))
                tokens.append(int(float(rec["Request tokens"])))
    csv_sha = sha256_file(Path(args.csv))
    for seed in args.windows:
        rng = random.Random(seed)
        start = rng.randrange(len(stamps) - n_arrivals)
        window = [(stamps[start + i] + rng.random(), tokens[start + i]) for i in range(n_arrivals)]
        window.sort()
        t0, t1 = window[0][0], window[-1][0]
        scaled = [((t - t0) / (t1 - t0) * args.span_ms, tok) for t, tok in window]
        by_len = sorted(range(n_arrivals), key=lambda i: (-scaled[i][1], i))[: len(groups)]
        doc_idx = sorted(by_len)  # time order
        chat_idx = [i for i in range(n_arrivals) if i not in set(doc_idx)]
        new_rows = []
        for g, i in zip(groups, doc_idx):
            t = int(scaled[i][0])
            for q, offset in (("q0", t), ("q1", t + args.q1_delay), ("q2", t + args.q2_delay)):
                new_rows.append(replace(docs[g][q], offset_ms=offset))
        for chat, i in zip(chats, chat_idx):
            new_rows.append(replace(chat, offset_ms=int(scaled[i][0])))
        new_rows.sort(key=lambda r: (r.offset_ms, r.request_id))
        name = f"{args.prefix}_w{seed}"
        write_trace(Path(args.trace_dir) / f"{name}.jsonl", new_rows)
        _, digest = load_trace(Path(args.trace_dir) / f"{name}.jsonl")
        times = sorted(r.offset_ms for r in new_rows if r.request_id.endswith("q0") or r.cls == "chat")
        gaps = [(b - a) / 1000 for a, b in zip(times, times[1:])]
        per_second = {}
        for t in times:
            per_second[t // 1000] = per_second.get(t // 1000, 0) + 1
        span_s = max(r.offset_ms for r in new_rows) / 1000
        manifest = {
            "trace": name, "trace_sha256": digest, "requests": len(new_rows), "span_ms": max(r.offset_ms for r in new_rows),
            "source": {"dataset": "BurstGPT_1.csv (HPMLL/BurstGPT)", "csv_sha256": csv_sha, "conversation_log_rows": len(stamps),
                       "window_seed": seed, "window_start_row": start, "window_rows": n_arrivals,
                       "window_real_span_s": t1 - t0, "rescaled_span_ms": args.span_ms,
                       "class_rule": "the 14 largest 'Request tokens' in the window are document first visits; the rest are chats",
                       "doc_request_tokens_range": [min(scaled[i][1] for i in doc_idx), max(scaled[i][1] for i in doc_idx)],
                       "chat_request_tokens_range": [min(scaled[i][1] for i in chat_idx), max(scaled[i][1] for i in chat_idx)]},
            "content": f"documents and chats copied from {args.src_trace}; q1 = q0 + {args.q1_delay} ms, q2 = q0 + {args.q2_delay} ms",
            "arrival_stats_independent_arrivals": {
                "count": len(times), "mean_gap_s": statistics.fmean(gaps), "gap_cv": statistics.pstdev(gaps) / statistics.fmean(gaps),
                "peak_arrivals_in_one_second": max(per_second.values())},
            "offered_rps_over_span": len(new_rows) / span_s,
            "arrival_times": "REAL arrival structure (BurstGPT window, jittered and rescaled); content from QuALITY/ShareGPT as in the source trace",
        }
        out = Path(args.manifest_dir) / f"{name}.manifest.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
        print(name, digest[:12], "span_ms", manifest["span_ms"], "offered_rps %.2f" % manifest["offered_rps_over_span"],
              "gap_cv %.2f" % manifest["arrival_stats_independent_arrivals"]["gap_cv"],
              "peak/s", manifest["arrival_stats_independent_arrivals"]["peak_arrivals_in_one_second"],
              "real window s", round(t1 - t0), "doc/chat req tokens", manifest["source"]["doc_request_tokens_range"], manifest["source"]["chat_request_tokens_range"])


if __name__ == "__main__":
    main()
