"""Use parent runtime generation, then explicitly select a new gateway policy."""
import subprocess
import sys
from pathlib import Path
import yaml


def main():
    args=sys.argv[1:];policy=None
    if '--policy' in args:
        index=args.index('--policy')+1;policy=args[index]
        if policy in {'packing_ready','ready_fifo'}:
            assert args[0] in {'configure','gateway'}
            args[index]='packing_reuse'
    subprocess.run([sys.executable,'scripts/v3_runtime.py',*args],check=True)
    if policy in {'packing_ready','ready_fifo'}:
        path=Path('.cacheflow-v3-gateway.yaml');c=yaml.safe_load(path.read_text());c['scheduler']['policy']=policy
        path.write_text(yaml.safe_dump(c,sort_keys=True));Path('.cacheflow-policy').write_text(policy+'\n')


if __name__=='__main__':main()
