"""Byte-explicit host-cache budgets; native APIs use different 'GB' units."""


def sglang_host_pool_bytes(native_gb,bytes_per_token,page_size=16):
    """Installed MHA HostKVCache: decimal GB, then always round up one page."""
    tokens=int(native_gb*1_000_000_000//bytes_per_token)
    return (tokens//page_size+1)*page_size*bytes_per_token


def lmcache_gib_flag(budget_bytes):
    """CLI float is multiplied by2**30; require an exact integer-byte round trip."""
    if not isinstance(budget_bytes,int) or not 0<budget_bytes<2**53:
        raise ValueError('byte budget must be a positive exactly representable integer')
    value=budget_bytes/(1<<30)
    result=format(value,'.17g')
    assert int(float(result)*(1<<30))==budget_bytes
    return result
