"""Per-request trace of the engine-queue demotion (patch log CACHEFLOW_ENGINE_DEMOTE_LOG) joined with the client's SLO outcomes.

Join: for each run, the engine log lists every request in the order it left the waiting queue (tier 0 chat, tier 1 savable document, tier 2 doomed
document) with its prompt token count and engine arrival time. The gateway trace gives each request's id, token count and dispatch order (the gateway
passes requests through in order). Engine entries are sorted by arrival time and matched to the gateway's document rows sorted by dispatch time; the match
is accepted only where the prompt token counts agree. Outcomes come from the client's per-request records.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

from .analyze import read_jsonl
from .real_analyze import _meets_slo


def gateway_rows(pattern: str, run_id: str):
    rows = []
    for path in glob.glob(pattern):
        with open(path, encoding="utf-8") as file:
            for line in file:
                if f'"{run_id}"' in line:
                    row = json.loads(line)
                    if row["run_id"] == run_id:
                        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="results/raw")
    parser.add_argument("--gateway-glob", default="results/raw/gateway_*_runs.jsonl")
    parser.add_argument("--out", default="results/real/engine_trace.json")
    args = parser.parse_args()
    raw = Path(args.raw_dir)
    logs = sorted(raw.glob("*.edemote.log"))
    total = {"demoted_missed": 0, "demoted_met": 0, "kept_missed": 0, "kept_met": 0, "unmatched": 0}
    per_run = []
    for log in logs:
        run_id = log.name.replace(".edemote.log", "")
        entries = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
        docs = sorted((e for e in entries if e["priority"] != 0), key=lambda e: e["arrival"])
        rows = sorted((r for r in gateway_rows(args.gateway_glob, run_id) if r.get("priority") == 1 and r.get("dispatch_ns")), key=lambda r: r["dispatch_ns"])
        records = {r["request_id"]: r for r in read_jsonl(raw / f"{run_id}.jsonl") if r["cls"] == "doc"}
        counts = {"demoted_missed": 0, "demoted_met": 0, "kept_missed": 0, "kept_met": 0, "unmatched": 0}
        examples = []
        for e, row in zip(docs, rows):
            rec = records.get(row["request_id"])
            if rec is None or e["tokens"] != row["input_tokens"]:
                counts["unmatched"] += 1
                continue
            met = bool(_meets_slo(rec))
            demoted = e["tier"] == 2
            counts[("demoted_" if demoted else "kept_") + ("met" if met else "missed")] += 1
            if demoted and met or (not demoted and not met):
                examples.append({"request_id": row["request_id"], "tier": e["tier"], "waited_s": round(e["waited_s"], 2), "ttft_ms": round(rec["arrival_ttft_ms"])})
        counts["entries"] = len(docs)
        counts["gateway_rows"] = len(rows)
        per_run.append({"run_id": run_id, **counts, "discordant_examples": examples[:6]})
        for k in total:
            total[k] += counts[k]
        print(f"{run_id:24s} docs {len(docs):2d} gw {len(rows):2d}  demoted: missed {counts['demoted_missed']} met {counts['demoted_met']} | kept: missed {counts['kept_missed']} met {counts['kept_met']} | unmatched {counts['unmatched']}")
    d, k = total["demoted_missed"] + total["demoted_met"], total["kept_missed"] + total["kept_met"]
    print(f"\ntotal: demoted documents {d} (missed {total['demoted_missed']}, still met {total['demoted_met']}); documents not demoted {k} (missed {total['kept_missed']}, met {total['kept_met']}); unmatched {total['unmatched']}")
    Path(args.out).write_text(json.dumps({"total": total, "runs": per_run}, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
