"""Freeze and execute full study only after verified terminal control audit."""
import argparse
import subprocess
import sys
import time
import psutil
from v6_after_main_native import alive


def main():
    p=argparse.ArgumentParser();p.add_argument('pid',type=int);a=p.parse_args();process=psutil.Process(a.pid)
    assert alive(process) and 'scripts/v6_after_native_controls.py' in process.cmdline();birth=process.create_time()
    print('Verified controls follow-on; full freeze/execution waits for complete controls',a.pid,flush=True)
    while alive(process):
        assert process.create_time()==birth;time.sleep(5)
    # The freezer verifies all development audits and original-union low-reuse
    # gates. Missing/failed evidence stops this dependency; it never retries.
    subprocess.run([sys.executable,'scripts/v6_freeze_full.py'],check=True)
    subprocess.run([sys.executable,'scripts/v6_full.py'],check=True)
    print('Full pipeline terminal; final research/report requirement audit remains',flush=True)


if __name__=='__main__':main()
