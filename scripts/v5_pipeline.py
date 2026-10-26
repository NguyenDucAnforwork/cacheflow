"""Execute fixed V5 validation, repaired-protocol repeats and the full study."""
import subprocess
import sys
from v5_verify import verify


def main():
    verify()
    for script in ['v5_validate.py','v5_audit_validation.py','v5_confirm.py','v5_audit_confirmation.py','v5_full.py']:
        verify();print('V5 PIPELINE',script,flush=True)
        subprocess.run([sys.executable,'scripts/'+script],check=True)


if __name__=='__main__':main()
