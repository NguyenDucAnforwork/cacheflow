from importlib.util import spec_from_file_location,module_from_spec
import pytest

spec=spec_from_file_location('v5_qos','scripts/v5_analyze_qos.py');module=module_from_spec(spec);spec.loader.exec_module(module)


def test_failed_response_never_disappears_from_slo_denominator_or_generates_quantiles():
    rows=[dict(status='ok',arrival_ttft_ms=100),dict(status='ok',arrival_ttft_ms=2000),
          dict(status='exception:ReadTimeout',arrival_ttft_ms=None)]
    s=module.summarize(rows,10)
    assert s['complete_success_quantiles'] is None and s['errors']==1
    assert s['qos'][0]['fraction_of_all_attempts']==pytest.approx(1/3)
    assert s['qos'][-1]['fraction_of_all_attempts']==pytest.approx(2/3)
    assert s['qos'][-1]['goodput_requests_per_s']==.2


def test_arrival_delay_counts_even_when_response_succeeds():
    s=module.summarize([dict(status='ok',arrival_ttft_ms=601000)],700)
    assert s['success_fraction']==1 and s['qos'][-1]['fraction_of_all_attempts']==0
    assert s['complete_success_quantiles']['p95_ms']==601000
