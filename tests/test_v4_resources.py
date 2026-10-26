import pytest
from cacheflow.v4_resources import sglang_host_pool_bytes,lmcache_gib_flag


def test_resource_apis_match_bytes_despite_decimal_vs_binary_unit_names():
    for gb,expected in [(16,16000745472),(48,48002236416)]:
        actual=sglang_host_pool_bytes(gb,147456)
        assert actual==expected
        assert 0<actual-gb*10**9<=16*147456
        assert int(float(lmcache_gib_flag(actual))*2**30)==actual
    assert lmcache_gib_flag(16*2**30)=='16'
    with pytest.raises(ValueError):lmcache_gib_flag(0)
