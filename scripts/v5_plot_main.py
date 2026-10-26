"""Plot audited main V5 dev gains alongside completion/decode tradeoffs."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    data=json.loads(Path('results/v3/v5r2_main_dev_findings.json').read_text())
    secondary=json.loads(Path('results/v3/v5r2_validation_secondary_metrics.json').read_text())
    assert data['requests']==1080 and not data['errors']
    arms=['fifo16','fifo64','lpm16','bundle16','dhas16','union64']
    groups=[[r for r in data['runs'] if r['arm']==arm] for arm in arms]
    second=[[r for r in secondary['runs'] if f'-main-qps4-{arm}-' in r['run_id']] for arm in arms]
    assert all(len(g)==3 for g in groups+second)
    fig,axes=plt.subplots(2,2,figsize=(12.5,8),layout='constrained')
    def bars(ax,series,colors,ylabel,title):
        width=.72/len(series)
        for j,((label,values),color) in enumerate(zip(series,colors)):
            x=np.arange(len(arms))+(j-(len(series)-1)/2)*width
            ax.bar(x,[np.mean(v) for v in values],width=width*.93,color=color,alpha=.85,label=label)
            for xx,ys in zip(x,values):ax.scatter([xx]*3,ys,s=10,color='#222222',zorder=3)
        ax.set_xticks(range(len(arms)),['FIFO16','FIFO64','GPU LPM16','Bundle16','DHAS16','Union64'],rotation=18)
        ax.set_ylabel(ylabel);ax.set_title(title);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.legend(fontsize=8)
    bars(axes[0,0],[(key.split('_')[0],[[r[key]/1000 for r in group] for group in groups]) for key in ['p50_ms','p95_ms','p99_ms']],
         ['#4477aa','#cc6677','#ddaa33'],'Arrival TTFT (s)','Arrival TTFT: mean of three run quantiles')
    bars(axes[0,1],[('Completion p95',[[r['completion_latency_ms']['p95']/1000 for r in group] for group in second])],
         ['#4477aa'],'Scheduled arrival to response close (s)','Completion latency also retains the tail gain')
    bars(axes[1,0],[('CPU consumed',[[r['consumed_cpu_tokens']/1000 for r in group] for group in groups]),
                       ('Computed',[[r['computed_tokens']/1000 for r in group] for group in groups])],
         ['#4477aa','#ddaa33'],'Tokens per run (thousands)','Engine source ledger; CPU tokens are not DMA bytes')
    bars(axes[1,1],[('Client TPOT proxy p95',[[r['client_tpot_proxy_ms']['p95'] for r in group] for group in second])],
         ['#cc6677'],'Request-level average decode proxy (ms/token)','Decode proxy worsens; not individual-token ITL')
    fig.suptitle('V5 revision2 main dev: 60 unique QA, three arrival schedules, 6 GiB GPU KV\nDots are serving schedules; decode proxy includes chunking and response-close overhead',fontsize=11)
    root=Path('results/v3/figures');root.mkdir(exist_ok=True)
    for ext in ['png','svg']:fig.savefig(root/f'v5r2_main_tradeoffs.{ext}',dpi=160)
    p=root/'v5r2_main_tradeoffs.svg';p.write_text('\n'.join(l.rstrip() for l in p.read_text().splitlines())+'\n')


if __name__=='__main__':main()
