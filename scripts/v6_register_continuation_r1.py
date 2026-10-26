"""Register the unchanged unexecuted suffix, after real archival revalidation."""
import json
import subprocess
import sys
import tempfile
from datetime import datetime,timezone
from pathlib import Path
from v6_freeze_full import verify_full,sha
from v6_full_analysis_r1 import FIRST,REGISTRATION,verify_revision,audit_configuration
from v6_full_continuation_r1 import PATH,retained_outcome,verify_continuation
from v6_full_load_r1 import load
from v6_raw_archive import expanded


def main():
    assert not PATH.exists()
    from v4_services import service_pid
    for name in ['cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache','cacheflow_v3_sglang']:assert service_pid(name)==0,name
    parent,seal,freeze=verify_full();verify_revision();outcome=retained_outcome()
    assert freeze['actions'][0]['run_id']==FIRST
    suffix=freeze['actions'][1:];assert len(suffix)==29 and sum(s['requests'] for s in suffix)==57594
    for step in suffix:
        base=Path('results/v3/sglang' if step['engine']=='sg' else 'results/v3')
        for ext in ['.setup.json','.invalid']:assert not (base/(step['run_id']+ext)).exists(),step['run_id']
    audit_path=Path(f'results/v3/{FIRST}.full_audit_r1.json');audit=json.loads(audit_path.read_text())
    with expanded(Path(f'results/v3/{FIRST}.archive_r1.json')) as archive:
        assert archive['audit_sha256']==sha(audit_path) and {r['path']:r['sha256'] for r in archive['files']}==audit['raw_sha256']
        for warm in [True,False]:
            rid=FIRST+('-warm' if warm else '')
            loaded=load(rid);setup=json.loads(Path(f'results/v3/{rid}.setup.json').read_text())
            entry=json.loads(Path(f'results/v3/{rid}.v6_entrypoint.json').read_text())
            audit_configuration(dict(freeze['actions'][0],run_id=rid),setup,loaded['summary'],entry,parent,seal,freeze,warm)
        with tempfile.TemporaryDirectory(prefix='v6full-r1-quality-') as directory:
            dest=Path(directory)/'quality.json'
            subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir','results/v3/raw','--run-ids',FIRST,'--output',str(dest)],check=True)
            assert json.loads(dest.read_text())==json.loads(Path(f'results/v3/{FIRST}.full_quality_r1.json').read_text())
    protocol=Path('docs/V6_FULL_ANALYSIS_R1.md')
    sources=['scripts/v6_full_continuation_r1.py','scripts/v6_continue_full_r1.py','scripts/v6_audit_full_r1.py','scripts/v6_register_continuation_r1.py']
    original_execution=json.loads(Path('results/v3/v6full1_execution.json').read_text())
    assert sha('/etc/supervisor/conf.d/cacheflow_v2_gateway.conf')==original_execution['original_supervisor_sha256']
    result=dict(status='registered_continuation_of_unexecuted_arms_no_retries',registered_utc=datetime.now(timezone.utc).isoformat(),
        reference_freeze_sha256=sha('results/v3/v6full1_freeze.json'),analysis_registration_sha256=sha(REGISTRATION),
        retained_outcome=outcome,remaining_actions=suffix,source_sha256={s:sha(s) for s in sources},protocol_path=str(protocol),protocol_sha256=sha(protocol),
        first_archive_revalidation=dict(files=10,measured_requests=1986,warmup_requests=60,official_quality_json_identical=True,request_integrity=True,configuration=True),
        scope='Only the original29unexecuted arms; original first arm reused byte-identically after explicit corrected analysis. No inference retry, treatment change, outcome selection, replacement study or completed-stage claim.')
    with PATH.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    verify_continuation();print('Registered continuation',sha(PATH),flush=True)


if __name__=='__main__':main()
