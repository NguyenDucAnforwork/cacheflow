from importlib.util import spec_from_file_location,module_from_spec
from types import SimpleNamespace
import pytest

spec=spec_from_file_location('v4_services','scripts/v4_services.py');module=module_from_spec(spec);spec.loader.exec_module(module)


def test_supervisor_stopped_pid_is_distinct_from_unknown_or_inconsistent_service(monkeypatch):
    def result(code,out):
        monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=code,stdout=out,stderr=''))
    result(7,'0\n');assert module.service_pid('test')==0
    result(0,'123\n');assert module.service_pid('test')==123
    result(7,'123')
    with pytest.raises(RuntimeError):module.service_pid('test')
    result(4,'ERROR (no such process)')
    with pytest.raises(RuntimeError):module.service_pid('test')
