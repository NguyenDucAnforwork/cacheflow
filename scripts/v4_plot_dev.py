"""Plot audited per-run latency tradeoffs; no request-level pseudo-replication."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

runs=json.loads(Path('results/v3/sglang/v4_direct_repl_audit.json').read_text())['runs']
by={r['run_id']:r for r in runs}
fig,axes=plt.subplots(1,3,figsize=(11,3.6),sharex=True)
for ax,metric in zip(axes,['p50_ms','p95_ms','p99_ms']):
    for seed,color in zip([101,102,103],['#0072B2','#D55E00','#009E73']):
        values=[by[f'v4-sgdirect-repl-{arm}-s{seed}'][metric]/1000 for arm in ['native','q4','q8']]
        ax.plot(range(3),values,'o-',color=color,label=f'seed {seed}',lw=1.5)
    ax.set_title(metric.replace('_ms','').upper()+' arrival TTFT')
    ax.set_xticks(range(3),['Native LPM','Packing q4','Packing q8'],rotation=15)
    ax.set_ylabel('seconds');ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.2)
axes[0].legend(frameon=False,fontsize=8)
fig.suptitle('DEV ONLY: Qwen3-4B / HiCache Direct / GPU KV 6 GiB / CPU 16 GiB\n60 unique QA, 3 arrival seeds at 4 QPS; tail gains have a median cost',fontsize=10)
fig.tight_layout()
for suffix in ['png','svg']:fig.savefig(f'results/v3/sglang/v4_direct_dev_tradeoff.{suffix}',dpi=160)
svg=Path('results/v3/sglang/v4_direct_dev_tradeoff.svg')
svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
