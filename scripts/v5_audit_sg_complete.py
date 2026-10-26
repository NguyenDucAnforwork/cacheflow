"""Aggregate all39 V5 native-engine validation runs after full evidence checks."""
import hashlib
import json
from pathlib import Path
from v5_validate import build_plan
from v5_verify import verify
from v5_audit_contracts import audit_common
from v4_audit_sglang_runs import audit


def main():
    parent,seal=verify();steps=[s for s in build_plan() if s['kind']=='sg' and '-warm-' not in s['run_id']]
    assert len(steps)==39;rows=[]
    for step in steps:
        rid=step['run_id'];setup=json.loads(Path(f'results/v3/sglang/{rid}.setup.json').read_text())
        summary=json.loads(Path(f'results/v3/raw/sglang/{rid}.summary.json').read_text())
        manifest=json.loads(Path(step['trace']).with_suffix('.manifest.json').read_text())
        audit_common(step,setup,summary,manifest,parent,seal);rows.append(audit(rid))
    inputs=['v5r2_primary_sg_audit','v5r2_lowload_audit','v5r2_lowreuse_audit','v5r2_abstention_audit','v5r2_dfs_audit','v5r2_gpufit_audit']
    seen=set();pairs=[];provenance={}
    for stem in inputs:
        path=Path(f'results/v3/{stem}.json');data=path.read_bytes();block=json.loads(data)
        block_ids={r['run_id'] for r in block['runs']};assert not (seen&block_ids)
        seen|=block_ids;pairs.extend(block['pairs']);provenance[str(path)]=hashlib.sha256(data).hexdigest()
    assert seen=={r['run_id'] for r in rows}
    low=json.loads(Path('results/v3/v5r2_lowreuse_audit.json').read_text())
    result=dict(scope='All39 SG validation runs only; main18, repair repeats and full evaluation remain separate. Repetitions reuse the same QA. Every arm has full source-fingerprint/actual transport coverage.',
        requests=sum(r['requests'] for r in rows),errors=0,low_reuse_gate_passed=low['declared_p95_gate_passed'],
        prompt_seal_sha256=hashlib.sha256(Path('results/v3/v5_prompt_freeze.json').read_bytes()).hexdigest(),
        constituent_audit_sha256=provenance,runs=rows,pairs=pairs)
    assert result['requests']==1740
    Path('results/v3/v5r2_sg_validation_complete.json').write_text(json.dumps(result,indent=2)+'\n')
    print('All39 SG validation runs audited',result['requests'],'requests; low-reuse gate',result['low_reuse_gate_passed'])


if __name__=='__main__':main()
