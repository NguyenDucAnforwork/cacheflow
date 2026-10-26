"""Analyze completed V5 pipeline; never starts/retries serving work or claims success."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
import psutil
from v5_verify import verify


def main():
    p=argparse.ArgumentParser();p.add_argument('pipeline_pid',type=int);a=p.parse_args()
    process=psutil.Process(a.pipeline_pid)
    assert 'scripts/v5_pipeline.py' in process.cmdline() and process.is_running()
    birth=process.create_time()
    print('Verified passive analysis waiter on pipeline',a.pipeline_pid,flush=True)
    while process.is_running() and process.status()!=psutil.STATUS_ZOMBIE:
        assert process.create_time()==birth,'PID reused'
        time.sleep(5)
    verify()
    def run(script,*args):
        subprocess.run([sys.executable,'scripts/'+script,*map(str,args)],check=True)
    for stage,n,requests in [('confirmation',27,1080),('full',17,33762)]:
        audit_path=Path(f'results/v3/v5r2_{stage}_audit.json')
        assert audit_path.exists(),f'Pipeline ended without {stage} audit; inspect failures, never auto-restart'
        audit=json.loads(audit_path.read_text())
        assert len(audit['runs'])==n and audit['requests']==requests and not audit['errors']
        run('v5_analyze_decode.py','--stage',stage,'--output',f'results/v3/v5r2_{stage}_secondary_metrics.json')
        run('v5_analyze_waits.py',audit_path,'--output',f'results/v3/v5r2_{stage}_waits.json')
        run('v5_run_intervals.py','--stage',stage)
        for row in audit['runs']:
            rid=row['run_id'];sg=(Path('results/v3/sglang')/f'{rid}.setup.json').exists()
            base=Path('results/v3/sglang' if sg else 'results/v3')
            run('v5_analyze_qos.py',rid,'--output',base/f'{rid}.qos.json')
            if sg:run('v4_analyze_sglang_resources.py',rid,'--output',base/f'{rid}.resources.json')
    run('v5_analyze_confirmation.py')
    full=json.loads(Path('results/v3/v5r2_full_audit.json').read_text())
    snapshots=[];missing=[]
    for row in full['runs']:
        rid=row['run_id'];base=Path('results/v3/sglang' if row['engine_kind']=='sg' else 'results/v3')
        path=base/f'{rid}.itl_histogram.json'
        if path.exists():snapshots.append(path)
        else:missing.append(rid)
    if snapshots:run('v5_analyze_histograms.py',*snapshots,'--output','results/v3/v5r2_full_native_itl.json')
    Path('results/v3/v5r2_postprocess_status.json').write_text(json.dumps(dict(
        scope='Derived analyses only; final research/report/quality/fairness review remains required',
        stages=['confirmation','full'],histogram_snapshots=len(snapshots),missing_histograms=missing,
        research_goal_complete=False),indent=2)+'\n')
    print('Derived V5 analyses complete; final scientific review remains required',flush=True)


if __name__=='__main__':main()
