from importlib.util import spec_from_file_location,module_from_spec
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path('scripts').resolve()))
spec=spec_from_file_location('v5_quality_scope','scripts/v4_compare_sglang.py')
module=module_from_spec(spec);spec.loader.exec_module(module)


def test_abstention_only_stratum_does_not_invent_an_answerable_f1():
    a=dict(answerable_f1=None,by_category={'5':dict(n=12,mean=.5)})
    b=dict(answerable_f1=None,by_category={'5':dict(n=12,mean=.75)})
    c=module.quality_contrast(a,b)
    assert c['a_f1'] is None and c['b_f1'] is None and c['f1_delta'] is None
    assert c['category5_delta']==.25


def test_missing_score_coverage_is_not_a_quality_gain():
    with pytest.raises(AssertionError):
        module.quality_contrast(dict(answerable_f1=None),dict(answerable_f1=.5))
