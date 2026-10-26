"""Finish the current V4 run, retire conflicted-prompt sweep, profile GPU kernels."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import psutil


def alive(process):
    try:return process.is_running() and process.status()!=psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:return False


def main():
    p=argparse.ArgumentParser();p.add_argument('--controller',type=int,required=True);p.add_argument('--bench',type=int,required=True);a=p.parse_args()
    controller=psutil.Process(a.controller);bench=psutil.Process(a.bench)
    assert 'scripts/v4_full.py' in controller.cmdline() and controller.status()==psutil.STATUS_STOPPED
    rid='v4c1-full-sg-g6-qps4-fifo-s901';assert rid in bench.cmdline()
    born=bench.create_time();print('Verified stopped controller and continuing FIFO benchmark',a.controller,a.bench,flush=True)
    while alive(bench):
        assert bench.create_time()==born
        time.sleep(5)
    # The stopped parent has not advanced to another arm. Preserve the completed
    # benchmark before terminating only that orchestration process.
    path=Path(f'results/v3/raw/sglang/{rid}.summary.json');s=json.loads(path.read_text())
    assert s['requests']==s['successes']==1986 and not s['errors']
    assert not Path(f'results/v3/sglang/{rid}.invalid').exists()
    assert controller.status()==psutil.STATUS_STOPPED and 'scripts/v4_full.py' in controller.cmdline()
    os.kill(a.controller,signal.SIGTERM);os.kill(a.controller,signal.SIGCONT)
    def call(*args):subprocess.run(list(args),check=True)
    call(sys.executable,'scripts/v4_audit_sglang_runs.py',rid,'--output','results/v3/sglang/v4_full_fifo_audit.json')
    call(sys.executable,'scripts/v2_quality_audit.py','--raw-dir','results/v3/raw/sglang','--run-ids',rid,
        '--output','results/v3/sglang/v4_full_fifo_quality.json')
    call('supervisorctl','stop','cacheflow_v2_gateway','cacheflow_v3_sglang')
    call('bash','scripts/v4_sglang_steady_profile.sh','kernel','v4_kernel_gpu_steady')
    call(sys.executable,'scripts/v4_analyze_kernel_overlap.py')
    print('V4 conflicted-prompt sweep retired; V4 full raw retained; kernel diagnostic complete. Ready for sealed V5 validation.',flush=True)


if __name__=='__main__':main()
