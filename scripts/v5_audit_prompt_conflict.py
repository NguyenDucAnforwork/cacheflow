"""Audit immutable V4 serialization conflict; do not reinterpret official scores."""
import hashlib
import json
from pathlib import Path
from cacheflow.locomo import load_locomo,context_prefix,question_prompt,trace_digest
from cacheflow.v2_replay import load_trace
from cacheflow.v5_prompt import LEGACY_FOOTER


def main():
    path=Path('data/processed/v3/v4-full4b-qps4-s901.jsonl.gz');rows=load_trace(path)
    manifest=json.loads(path.with_suffix('.manifest.json').read_text());assert trace_digest(rows)==manifest['trace_sha256']
    conversations={c.sample_id:c for c in load_locomo('data/raw/locomo10.json')}
    conflicts=0
    for r in rows:
        c=conversations[r.sample_id];q=c.questions[r.qa_index]
        exact_user=question_prompt(context_prefix(c),q)
        assert r.prompt.count(exact_user)==1 and context_prefix(c).endswith(LEGACY_FOOTER)
        assert 'answer "No information available."' in r.prompt
        conflicts+=1
    base=Path('results/v3/raw/sglang');rid='v4c1-full-sg-g6-qps4-native-s901'
    requests={r['request_id']:r for r in map(json.loads,(base/f'{rid}.jsonl').read_text().splitlines())}
    outputs={r['request_id']:r for r in map(json.loads,(base/f'{rid}.outputs.jsonl').read_text().splitlines())}
    category5=[r for r in requests.values() if r['category']==5]
    texts=[]
    for r in category5:
        text=outputs[r['request_id']]['output'];assert hashlib.sha256(text.encode()).hexdigest()==r['output_hash'];texts.append(text)
    result=dict(scope='Immutable V4 protocol diagnosis. Format diagnostic only; official evaluator scores are unchanged. No semantic abstention equivalence or corrected leaderboard score.',
        trace_sha256=manifest['trace_sha256'],requests=len(rows),conflicting_instructions=conflicts,
        system_abstention='No information available.',user_abstention="I don't know",category5_requests=len(texts),
        exact_legacy_response=sum(t.strip().rstrip('.').lower()=="i don't know" for t in texts),
        contains_legacy_response=sum("i don't know" in t.lower() for t in texts),
        official_accepted_phrase=sum(any(p in t.lower() for p in ['no information available','not mentioned']) for t in texts),
        status='V4 retained as historical conflicting-prompt protocol; V5 must validate consistent instructions prospectively with unchanged method')
    out=Path('results/v3/v4_prompt_conflict_audit.json');out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
