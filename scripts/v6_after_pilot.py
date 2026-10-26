"""Wait on verified pilot; audit complete outcomes without restarting GPU work."""
import argparse
import subprocess
import sys
import time
import psutil


def main():
    p=argparse.ArgumentParser();p.add_argument('pid',type=int);a=p.parse_args()
    process=psutil.Process(a.pid);assert process.is_running() and 'scripts/v6_pilot.py' in process.cmdline();birth=process.create_time()
    print('Verified V6 pilot analysis waiter',a.pid,flush=True)
    while process.is_running() and process.status()!=psutil.STATUS_ZOMBIE:
        assert process.create_time()==birth;time.sleep(5)
    subprocess.run([sys.executable,'scripts/v6_audit_pilot.py'],check=True)
    print('Pilot audited; strong-baseline replication, controls and full study remain required',flush=True)


if __name__=='__main__':main()
