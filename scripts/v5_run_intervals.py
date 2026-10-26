"""Exploratory paired-run log-ratio intervals; never request-level bootstrapping."""
import json
import argparse
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
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['validation','confirmation','full'],default='validation');args=p.parse_args()
    audit=json.loads(Path(f'results/v3/v5r2_{args.stage}_audit.json').read_text())
    n,requests={'validation':(57,2820),'confirmation':(27,1080),'full':(17,33762)}[args.stage]
    assert len(audit['runs'])==n and audit['requests']==requests and not audit['errors']
    by={r['run_id']:r for r in audit['runs']};groups=defaultdict(list)
    pairs=list(audit['pairs'])
    if args.stage=='confirmation':
        # The integrity audit's same-process comparator excludes native DFS.
        # Add the audited fresh-process ordering competitor explicitly.
        for seed in [701,702,703]:
            left=f'v5r2-confirm-sg-dfs-qps4-native-s{seed}';right=f'v5r2-confirm-sg-lpm-qps4-union-s{seed}'
            assert by[left]['trace_sha256']==by[right]['trace_sha256']
            pairs.append(dict(a=left,b=right))
    assert len({(pair['a'],pair['b']) for pair in pairs})==len(pairs)
    for pair in pairs:groups[(pair['a'].rsplit('-s',1)[0],pair['b'].rsplit('-s',1)[0])].append(pair)
    rows=[]
    for (a,b),pairs in groups.items():
        pairs.sort(key=lambda p:int(p['a'].rsplit('-s',1)[1]));assert len(pairs) in [1,3]
        rows.append(dict(baseline=a,candidate=b,metrics={key:paired_log_interval(
            [by[p['a']][key] for p in pairs],[by[p['b']][key] for p in pairs]) for key in ['p50_ms','p95_ms','p99_ms']}))
    result=dict(stage=args.stage,scope='Conditional serving-run variability across3 paired arrival schedules on fixed QA/model/host. Processes may be reused or restarted; these are not independent host or semantic-data replications. n3 intervals are assumption-dependent descriptors, not robust population inference or quality-equivalence tests. Single-pair controls have null intervals.',comparisons=rows)
    Path(f'results/v3/v5r2_{args.stage}_run_intervals.json').write_text(json.dumps(result,indent=2)+'\n')
    for r in rows:print(r['baseline'],r['metrics']['p95_ms'])


if __name__=='__main__':main()
