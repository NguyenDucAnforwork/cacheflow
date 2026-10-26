"""Plot audited V5 revision2 SG dev quantiles with the median cost visible."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    data=json.loads(Path('results/v3/v5r2_primary_sg_audit.json').read_text())
    assert data['requests']==540 and not data['errors'] and len(data['runs'])==9
    groups=[[r for r in data['runs'] if f'-{arm}-s' in r['run_id']] for arm in ['native','fifo','union']]
    pairs=[r for r in data['pairs'] if '-native-' in r['a']];assert len(pairs)==3
    fig,axes=plt.subplots(1,2,figsize=(11,4.6),layout='constrained')
    colors=['#4477aa','#cc6677','#ddaa33'];metrics=['p50_ms','p95_ms','p99_ms']
    for j,(key,color) in enumerate(zip(metrics,colors)):
        x=np.arange(3)+(j-1)*.25
        values=[[r[key]/1000 for r in rows] for rows in groups]
        axes[0].bar(x,[np.mean(v) for v in values],width=.23,label=key.split('_')[0],color=color,alpha=.8)
        for xx,ys in zip(x,values):axes[0].scatter([xx]*len(ys),ys,s=14,c='#222222',zorder=3)
        axes[1].bar(x,[r[key+'_delta_pct'] for r in pairs],width=.23,label=key.split('_')[0],color=color,alpha=.8)
    axes[0].set_xticks(range(3),['Native LPM','FIFO64 + LPM','Union64 + LPM'])
    axes[0].set_ylabel('Arrival TTFT (seconds)');axes[0].set_title('Mean of run quantiles; dots are serving seeds')
    axes[1].set_xticks(range(3),['Seed101','Seed102','Seed103']);axes[1].axhline(0,color='black',lw=.7)
    axes[1].set_ylabel('Union vs native change (%)');axes[1].set_title('Tail improvement comes with median cost')
    for ax in axes:ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.legend()
    fig.suptitle('V5 revision2 dev: 60 unique QA, three arrival schedules, same Direct + guard backend',fontsize=11)
    root=Path('results/v3/figures');root.mkdir(exist_ok=True)
    for suffix in ['png','svg']:fig.savefig(root/f'v5r2_primary_tradeoffs.{suffix}',dpi=160)
    svg=root/'v5r2_primary_tradeoffs.svg';svg.write_text('\n'.join(l.rstrip() for l in svg.read_text().splitlines())+'\n')


if __name__=='__main__':main()
