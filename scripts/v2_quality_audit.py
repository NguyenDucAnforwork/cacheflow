"""Score private captured generations with the pinned original LoCoMo evaluator.

Only scoring definitions are executed, avoiding unrelated BERTScore model imports.
No prompt, gold answer, or generated text is written to tracked summaries.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import statistics
import string
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import numpy as np
import regex
from nltk.stem import PorterStemmer

from cacheflow.locomo import load_locomo

EVALUATOR_SHA256 = '8e3be5d57ff2ff9ec5cd05939592f468c5f3f1fd95d13e431932bdf6bf0fd6fd'
EVALUATOR_URL = ('https://raw.githubusercontent.com/snap-research/locomo/'
                 '3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/task_eval/evaluation.py')


def evaluator(path):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EVALUATOR_SHA256:
        raise ValueError('evaluator SHA mismatch')
    tree = ast.parse(raw)
    names = {'normalize_answer', 'f1_score', 'f1', 'eval_question_answering'}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {n.name for n in functions} != names:
        raise ValueError('evaluator missing scoring functions')
    scope = dict(regex=regex, string=string, Counter=Counter, np=np, ps=PorterStemmer())
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), scope)
    return scope['eval_question_answering']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, default=Path('data/raw/locomo10.json'))
    p.add_argument('--evaluator', type=Path, default=Path('data/processed/v2/evaluator/evaluation.py'))
    p.add_argument('--run-ids', nargs='+', required=True)
    p.add_argument('--output', type=Path, default=Path('results/v2/e2_quality.json'))
    args = p.parse_args()
    score = evaluator(args.evaluator)
    conversations = {c.sample_id:c for c in load_locomo(args.source)}
    source_sha = hashlib.sha256(args.source.read_bytes()).hexdigest()
    summaries = []
    for run_id in args.run_ids:
        base = Path('results/v2/raw')
        summary = json.loads((base / f'{run_id}.summary.json').read_text())
        if summary['source_sha256'] != source_sha or summary['errors']:
            raise ValueError('source mismatch or failed run')
        requests = {r['request_id']:r for r in map(json.loads, (base / f'{run_id}.jsonl').read_text().splitlines())}
        outputs = {r['request_id']:r for r in map(json.loads, (base / f'{run_id}.outputs.jsonl').read_text().splitlines())}
        if requests.keys() != outputs.keys():
            raise ValueError('output IDs mismatch')
        qas = []
        per_request = []
        for rid in sorted(requests):
            r = requests[rid]
            text = outputs[rid]['output']
            if hashlib.sha256(text.encode()).hexdigest() != r['output_hash']:
                raise ValueError('output hash mismatch')
            q = conversations[r['sample_id']].questions[r['qa_index']]
            # The original evaluator accesses answer even for category 5.
            qas.append(dict(answer=q.answer or q.adversarial_answer or '', category=q.category, prediction=text))
            per_request.append(dict(request_id=rid, sample_id=r['sample_id'], category=q.category,
                                    budget_hit=r['output_tokens'] == summary['output_tokens_budget']))
        scores, _, _ = score(qas)
        for row, value in zip(per_request, scores):
            row['score'] = float(value)
        by_category = {}
        for category in sorted({r['category'] for r in per_request}):
            values = [r['score'] for r in per_request if r['category'] == category]
            by_category[str(category)] = dict(n=len(values), mean=statistics.mean(values))
        answerable = [r['score'] for r in per_request if r['category'] != 5]
        summaries.append(dict(run_id=run_id, answerable_n=len(answerable),
                              protocol=summary['protocol'], prompt_version=summary['prompt_version'],
                              trace_sha256=summary['trace_sha256'],
                              answerable_f1=statistics.mean(answerable) if answerable else None,
                              by_category=by_category,
                              output_budget_hits=sum(r['budget_hit'] for r in per_request),
                              per_request=per_request))
    result = dict(evaluator_url=EVALUATOR_URL, evaluator_sha256=EVALUATOR_SHA256,
                  nltk_version=version('nltk'), source_sha256=source_sha,
                  scope='LoCoMo text-only serving subsets; protocol and prompt version per run; raw budgeted outputs, no answer extraction; not leaderboard',
                  runs=summaries)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print('Wrote', args.output, 'runs', len(summaries))


if __name__ == '__main__':
    main()
