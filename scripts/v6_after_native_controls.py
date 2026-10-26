"""Verified dependency: run main controls only after audited native completion."""
import argparse
import subprocess
import sys
import time
import psutil
from v6_after_main_native import alive


def main():
    p=argparse.ArgumentParser();p.add_argument('pid',type=int);a=p.parse_args()
    process=psutil.Process(a.pid);assert alive(process) and 'scripts/v6_after_main_native.py' in process.cmdline()
    birth=process.create_time();print('Verified native follow-on handle; main controls wait for terminal audit',a.pid,flush=True)
    while alive(process):
        assert process.create_time()==birth;time.sleep(5)
    # The controller requires a complete45-arm native audit and idle services.
    subprocess.run([sys.executable,'scripts/v6_main_controls.py'],check=True)
    subprocess.run([sys.executable,'scripts/v6_audit_main_controls.py'],check=True)
    print('Main controls audited; full protocol freeze/evaluation still required',flush=True)


if __name__=='__main__':main()
