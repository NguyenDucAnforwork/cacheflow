"""Require the full33-run guarded validation matrix, with explicit legacy-label aliases."""
import json
import statistics
import subprocess
import sys
from pathlib import Path
from v4_audit_sglang_runs import audit
from v4_compare_sglang import compare

aliases=json.loads(Path('results/v3/sglang/v4_validation_aliases.json').read_text())['aliases']
plan=subprocess.check_output(['bash','scripts/v4_sglang_validate.sh','--plan'],text=True)
entries=[line.split('\t') for line in plan.splitlines() if line.startswith('BENCH\t') and '-warm-' not in line]
assert len(entries)==33 and len({e[1] for e in entries})==33
runs=[];lookup={}
for _,canonical,trace in entries:
    actual=aliases.get(canonical,canonical);checked=audit(actual)
    manifest=json.loads(Path(trace).with_suffix('.manifest.json').read_text())
    assert checked['trace_sha256']==manifest['trace_sha256']
    runtime=checked['runtime']
    expected_policy='dfs-weight' if '-dfs-weight-' in canonical else 'lpm'
    assert runtime['schedule_policy']==expected_policy and runtime['same_batch_guard']
    assert not runtime['profile_transfers'] and runtime['host_kv_gib']==16
    assert runtime['gpu_kv_gib']==(10 if '-gpufit-' in canonical else 6)
    assert runtime['max_running_requests']==16 and runtime['io_backend']=='direct' and runtime['attention_backend']=='flashinfer'
    if '-union-' in canonical:
        assert checked['gateway_policy']=='packing_reuse' and checked['gateway_prepare_mode']=='thread'
        assert checked['admission']['max_inflight']==64 and checked['admission']['max_head_bypasses']<=8
    elif '-fifo-' in canonical:
        assert checked['gateway_policy']=='fifo' and checked['gateway_prepare_mode']=='thread'
        assert checked['admission']['max_inflight']==64
    else:assert checked['gateway_policy'] is None
    checked['canonical_id']=canonical;runs.append(checked);lookup[canonical]=actual
out=Path('results/v3/sglang/v4_validation_quality.json')
subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir','results/v3/raw/sglang',
    '--run-ids',*[r['run_id'] for r in runs],'--output',str(out)],check=True)
quality={r['run_id']:r for r in json.loads(out.read_text())['runs']}
pairs=[]
for canonical,actual in lookup.items():
    if '-union-' not in canonical:continue
    native=canonical.replace('-union-','-native-')
    result=compare(lookup[native],actual,quality);result['canonical_b']=canonical;pairs.append(result)
    fifo=canonical.replace('-union-','-fifo-')
    if fifo in lookup:
        result=compare(lookup[fifo],actual,quality);result['canonical_b']=canonical;pairs.append(result)
result=dict(scope='Guarded V4 dev validation:33 audited measured runs;8 labels resolved by preserved source metadata, no raw renaming',
    requests=sum(r['requests'] for r in runs),errors=0,runs=runs,pairs=pairs)
Path('results/v3/sglang/v4_validation_audit.json').write_text(json.dumps(result,indent=2)+'\n')
for pair in pairs:print(pair['a'],pair['b'],round(pair['p95_ms_delta_pct'],3),round(pair['p99_ms_delta_pct'],3),round(pair['f1_delta'],5))
