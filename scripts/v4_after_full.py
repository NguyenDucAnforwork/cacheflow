"""Wait on the verified full driver, then analyze completed profiling/resources.

Never retries or restarts GPU work. A missing full audit or kernel diagnostic is
an incomplete pipeline, not an inference that the GPU benchmark succeeded.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
import psutil
from v4_full import build_plan


def main():
    p=argparse.ArgumentParser();p.add_argument('pid',type=int);a=p.parse_args()
    driver=psutil.Process(a.pid)
    assert 'scripts/v4_full.py' in driver.cmdline() and driver.is_running()
    started=driver.create_time()
    print('Verified full driver',a.pid,started,flush=True)
    while driver.is_running() and driver.status()!=psutil.STATUS_ZOMBIE:
        assert driver.create_time()==started,'PID reused'
        time.sleep(5)
    path=Path('results/v3/v4_full_audit.json')
    assert path.exists(),'Full driver ended without a successful complete-study audit; inspect retained errors, do not restart blindly'
    audit=json.loads(path.read_text());assert audit['requests']==33762 and len(audit['runs'])==17 and not audit['errors']
    subprocess.run([sys.executable,'scripts/v4_analyze_kernel_overlap.py'],check=True)
    for step in build_plan():
        if step['kind']=='sg' and '-warm-' not in step['run_id']:
            rid=step['run_id']
            subprocess.run([sys.executable,'scripts/v4_analyze_sglang_resources.py',rid,
                '--output',f'results/v3/sglang/{rid}.resources.json'],check=True)
    print('Full resource and kernel timeline analysis completed',flush=True)


if __name__=='__main__':main()
