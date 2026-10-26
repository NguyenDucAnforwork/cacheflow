"""Summarize paired subset QA scores at run level, retaining all mismatches."""
import argparse
import json
import statistics
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    quality = json.loads(args.input.read_text())
    runs = {r['run_id']: r for r in quality['runs']}
    pairs = []
    for run_id, a in runs.items():
        if '-b1-' not in run_id:
            continue
        other = run_id.replace('-b1-', '-b2-')
        if other not in runs:
            raise ValueError(f'missing paired quality arm: {other}')
        b = runs[other]
        x = {r['request_id']: r for r in a['per_request']}
        y = {r['request_id']: r for r in b['per_request']}
        if x.keys() != y.keys():
            raise ValueError('quality request IDs mismatch')
        changed = [dict(request_id=rid, b1_score=x[rid]['score'], b2_score=y[rid]['score'],
                        delta=y[rid]['score']-x[rid]['score']) for rid in sorted(x)
                   if x[rid]['score'] != y[rid]['score']]
        pairs.append(dict(b1=run_id, b2=other, requests=len(x),
                          b1_f1=a['answerable_f1'], b2_f1=b['answerable_f1'],
                          delta_f1=b['answerable_f1']-a['answerable_f1'],
                          b1_budget_hits=a['output_budget_hits'], b2_budget_hits=b['output_budget_hits'],
                          score_changed_requests=changed))
    args.output.write_text(json.dumps(dict(
        note='Repeated seeds reuse the same QA; these are paired run-level scores, not new independent QA samples.',
        evaluator_sha256=quality['evaluator_sha256'], pairs=pairs),indent=2)+'\n')
    for p in pairs:
        print(p['b1'], f"F1 {p['b1_f1']:.5f} -> {p['b2_f1']:.5f}",
              'changed-score requests',len(p['score_changed_requests']))


if __name__ == '__main__':
    main()
