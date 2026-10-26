"""Exploratory paired-run log-ratio intervals; never request-level bootstrapping."""
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def paired_log_interval(a,b):
    assert len(a)==len(b) and all(x>0 for x in [*a,*b])
    if len(a)!=3:return None
    values=[math.log(y/x) for x,y in zip(a,b)]
    # Student t(df=2), quantile .975, from its analytic CDF.
    u=.95;tcrit=math.sqrt(2)*u/math.sqrt(1-u*u)
    center=statistics.mean(values);half=tcrit*statistics.stdev(values)/math.sqrt(3)
    return dict(paired_runs=3,geometric_ratio_delta_pct=100*math.expm1(center),
        exploratory_t95_low_pct=100*math.expm1(center-half),exploratory_t95_high_pct=100*math.expm1(center+half),
        method='t(df2) interval on paired log ratios; normality/independence assumptions unverified at n3',
        per_seed_ratio_delta_pct=[100*(y/x-1) for x,y in zip(a,b)])


def main():
    audit=json.loads(Path('results/v3/v5r2_validation_audit.json').read_text())
    assert audit['requests']==2820 and not audit['errors']
    by={r['run_id']:r for r in audit['runs']};groups=defaultdict(list)
    for pair in audit['pairs']:groups[(pair['a'].rsplit('-s',1)[0],pair['b'].rsplit('-s',1)[0])].append(pair)
    rows=[]
    for (a,b),pairs in groups.items():
        pairs.sort(key=lambda p:int(p['a'].rsplit('-s',1)[1]));assert len(pairs)==3
        rows.append(dict(baseline=a,candidate=b,metrics={key:paired_log_interval(
            [by[p['a']][key] for p in pairs],[by[p['b']][key] for p in pairs]) for key in ['p50_ms','p95_ms','p99_ms']}))
    result=dict(scope='Conditional serving-run variability across3 paired arrival schedules on fixed QA/model/host. Same serving process is reused within a backend; these are not independent host/process or semantic-data replications. n3 intervals are assumption-dependent descriptors, not robust population inference or quality-equivalence tests.',comparisons=rows)
    Path('results/v3/v5r2_validation_run_intervals.json').write_text(json.dumps(result,indent=2)+'\n')
    for r in rows:print(r['baseline'],r['metrics']['p95_ms'])


if __name__=='__main__':main()
