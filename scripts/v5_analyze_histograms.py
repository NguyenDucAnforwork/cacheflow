"""Validate passive native histograms and report interval bounds, not fake quantiles."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def quantile_bounds(buckets,count,q):
    assert count>0 and 0<q<1
    points=sorted((float(k),v) for k,v in buckets.items())
    assert points and math.isinf(points[-1][0]) and points[-1][0]>0 and points[-1][1]==count
    assert all(math.isfinite(v) and v>=0 for _,v in points)
    assert all(a[1]<=b[1] for a,b in zip(points,points[1:])), 'nonmonotonic cumulative histogram'
    assert points[0][0]>=0, 'latency bucket must be nonnegative'
    lower=0
    for upper,value in points:
        if value>=count*q:
            return dict(lower_ms=lower*1000,upper_ms=upper*1000 if math.isfinite(upper) else None,
                        upper_unbounded=not math.isfinite(upper),scope='Histogram observation quantile lies within these bucket boundaries; no interpolation or exact token percentile.')
        lower=upper
    raise AssertionError('incomplete histogram')


def analyze(path):
    blob=path.read_bytes();data=json.loads(blob)
    result=dict(run_id=data['run_id'],snapshot_sha256=hashlib.sha256(blob).hexdigest(),
                coverage_valid=data['coverage_valid'],coverage_failures=data['coverage_failures'])
    if not data['coverage_valid']:
        result.update(native_itl_mean_ms=None,quantile_bounds=None)
        return result
    assert data['before']['pid']==data['after']['pid'] and data['before']['end_ns']<data['after']['start_ns']
    buckets=data['native_itl_cumulative_bucket_deltas'];count=data['itl_observations']
    result.update(native_itl_mean_ms=data['native_itl_mean_ms'],itl_observations=count,
                  quantile_bounds={f'p{p}':quantile_bounds(buckets,count,p/100) for p in [50,95,99]})
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('snapshots',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    rows=[analyze(path) for path in a.snapshots];assert len({r['run_id'] for r in rows})==len(rows)
    a.output.write_text(json.dumps(dict(scope='Passive full-run native ITL buckets. Coverage failures stay null. Per-token engine observations differ from per-request client TPOT proxies.',runs=rows),indent=2)+'\n')


if __name__=='__main__':main()
