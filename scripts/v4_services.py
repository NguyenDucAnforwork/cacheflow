"""Read supervisor PID without mistaking the documented stopped exit for failure."""
import subprocess


def service_pid(name):
    result=subprocess.run(['supervisorctl','pid',name],capture_output=True,text=True)
    value=result.stdout.strip()
    if result.returncode not in {0,7} or not value.isdigit():
        raise RuntimeError(f'Cannot establish service PID for {name}: {result.returncode} {value} {result.stderr[:200]}')
    pid=int(value)
    if result.returncode==7 and pid!=0:
        raise RuntimeError(f'Unexpected stopped status for live PID: {name} {pid}')
    return pid
