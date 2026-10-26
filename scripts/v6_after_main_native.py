"""Verify existing main/analysis handles, then execute one native study, no retries."""
import argparse
import subprocess
import sys
import time
import psutil


def alive(process):
    try:return process.is_running() and process.status()!=psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:return False


def main():
    p=argparse.ArgumentParser();p.add_argument('main_pid',type=int);p.add_argument('audit_pid',type=int);a=p.parse_args()
    handles=[]
    for pid,script in [(a.main_pid,'scripts/v6_main_matrix.py'),(a.audit_pid,'scripts/v6_after_main_matrix.py')]:
        process=psutil.Process(pid);assert alive(process) and script in process.cmdline()
        handles.append((process,process.create_time()))
    print('Verified main and audit handles; native launch waits for both terminal',flush=True)
    while any(alive(process) for process,_ in handles):
        for process,birth in handles:
            if alive(process):assert process.create_time()==birth
        time.sleep(5)
    # Controller independently checks the complete audit and idle services before
    # registering or mutating anything. Missing/failed audit stops, never retries.
    subprocess.run([sys.executable,'scripts/v6_native_matrix.py'],check=True)
    subprocess.run([sys.executable,'scripts/v6_audit_native_matrix.py'],check=True)
    print('Native validation and audit done; final method/full benchmark remain',flush=True)


if __name__=='__main__':main()
