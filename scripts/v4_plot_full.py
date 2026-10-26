"""Plot full primary results only after every frozen full run passes its audit."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    audit=json.loads(Path('results/v3/v4_full_audit.json').read_text())
    assert len(audit['runs'])==17 and audit['requests']==33762 and not audit['errors']
    quality={r['run_id']:r for r in json.loads(Path('results/v3/v4_full_sg_quality.json').read_text())['runs']}
    arms=['native','fifo','dfs','union'];labels=['Native LPM','FIFO64 + LPM','Native DFS','Union64 + LPM']
    groups=[[r for r in audit['runs'] if r['run_id'].startswith(f'v4c1-full-sg-g6-qps4-{arm}-')] for arm in arms]
    assert all(len(rows)==3 for rows in groups)
    fig,axes=plt.subplots(1,3,figsize=(15,4.8),layout='constrained')
    def bars(ax,series):
        width=.8/len(series)
        for j,(metric,title,color) in enumerate(series):
            x=np.arange(4)+(j-(len(series)-1)/2)*width
            values=[[metric(r) for r in rows] for rows in groups]
            ax.bar(x,[np.mean(v) for v in values],width=width*.94,label=title,color=color,alpha=.8)
            for xx,v in zip(x,values):ax.scatter([xx]*len(v),v,s=12,color='#222222',zorder=4)
        ax.set_xticks(range(4),labels,rotation=15,ha='right');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.legend()
    bars(axes[0],[(lambda r:r['p50_ms']/1000,'p50','#4477aa'),(lambda r:r['p95_ms']/1000,'p95','#cc6677')])
    axes[0].set_ylabel('Arrival TTFT (seconds)');axes[0].set_title('Run-level latency quantiles')
    bars(axes[1],[(lambda r:r['duration_s'],'Makespan','#228833')]);axes[1].set_ylabel('Seconds');axes[1].set_title('Workload completion time')
    bars(axes[2],[(lambda r:quality[r['run_id']]['answerable_f1'],'Answerable F1','#4477aa'),
        (lambda r:quality[r['run_id']]['by_category']['5']['mean'],'Category5 score','#ddaa33')])
    axes[2].set_ylabel('Pinned evaluator score');axes[2].set_ylim(0,1);axes[2].set_title('Raw outputs, cap96; separate metrics')
    fig.suptitle('Full text-only LoCoMo: 1,986 QA, three arrival schedules, 6GiB GPU KV',fontsize=12)
    root=Path('results/v3/figures');root.mkdir(exist_ok=True)
    for suffix in ['png','svg']:fig.savefig(root/f'v4_full_primary.{suffix}',dpi=160)
    svg=root/'v4_full_primary.svg';svg.write_text('\n'.join(l.rstrip() for l in svg.read_text().splitlines())+'\n')


if __name__=='__main__':main()
