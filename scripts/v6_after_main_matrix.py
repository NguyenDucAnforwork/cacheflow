"""Verified read-only follow-on analysis, with no serving retries or completion claim."""
import argparse
import subprocess
import sys
import time
import psutil


def main():
    p=argparse.ArgumentParser();p.add_argument('pid',type=int);a=p.parse_args();process=psutil.Process(a.pid)
    assert process.is_running() and 'scripts/v6_main_matrix.py' in process.cmdline();birth=process.create_time()
    print('Verified main matrix analysis waiter',a.pid,flush=True)
    while process.is_running() and process.status()!=psutil.STATUS_ZOMBIE:
        assert process.create_time()==birth;time.sleep(5)
    subprocess.run([sys.executable,'scripts/v6_audit_main_matrix.py'],check=True)
    print('Main development audit done; controls/native/full research evaluation still required',flush=True)


if __name__=='__main__':main()
