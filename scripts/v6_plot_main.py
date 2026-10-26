"""Plot only the complete audited24-arm V6 development matrix."""
import json
import statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    p=json.loads(Path('results/v3/v6dev1_main_audit.json').read_text());assert p['requests']==1440 and p['errors']==0 and len(p['runs'])==24
    arms=['fifo16','fifo64','lpm16','bundle16','dhas16','union64','ready_fifo','packing_ready']
    names=['FIFO16','FIFO64','GPU LPM16','Bundle16','DHAS16','Union64','Ready FIFO','Ready union']
    colors=['#89929b','#89929b','#46688c','#dc9c42','#a7adb5','#378469','#8d75ac','#2b73a4']
    by={r['arm']:r for r in p['aggregate']};secondary={r['run_id']:r for r in p['secondary']};x=np.arange(len(arms))
    fig,axs=plt.subplots(2,2,figsize=(13,8.5));fig.subplots_adjust(bottom=.18,hspace=.4,wspace=.25)
    ax=axs[0,0]
    ax.bar(x-.17,[by[a]['p50_ms']/1000 for a in arms],width=.34,color=colors,alpha=.45,label='p50')
    ax.bar(x+.17,[by[a]['p95_ms']/1000 for a in arms],width=.34,color=colors,label='p95')
    for i,a in enumerate(arms):
        values=[r['p95_ms']/1000 for r in p['runs'] if r['arm']==a];ax.scatter([i+.17]*3,values,c='black',s=10,zorder=3)
    ax.set_title('A. Scheduled-arrival TTFT');ax.set_ylabel('Seconds');ax.legend(frameon=False)
    plots=[(axs[0,1],'B. Engine-consumed CPU KV','Thousand tokens',lambda r:r['consumed_cpu_tokens']/1000),
        (axs[1,0],'C. Response completion p95','Seconds',lambda r:secondary[r['run_id']]['completion_latency_ms']['p95']/1000),
        (axs[1,1],'D. Client TPOT proxy p95','Milliseconds / output token',lambda r:secondary[r['run_id']]['client_tpot_proxy_ms']['p95'])]
    for ax,title,ylabel,value in plots:
        values=[[value(r) for r in p['runs'] if r['arm']==a] for a in arms]
        ax.bar(x,[statistics.mean(v) for v in values],color=colors)
        for i,v in enumerate(values):ax.scatter([i]*3,v,c='black',s=10,zorder=3)
        ax.set_title(title);ax.set_ylabel(ylabel)
    for ax in axs.flat:
        ax.set_xticks(x,names,rotation=28,ha='right',fontsize=9);ax.spines[['right','top']].set_visible(False);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('V6 development: union saves CPU-source work; decode costs remain',fontsize=15)
    fig.text(.07,.05,'60 previously exposed QA, three arrival schedules, 24 fresh engines; separate warmups excluded.\nBars are means of run quantiles (panel B: source-token counts); dots are individual runs.\nClient TPOT is a request-level proxy, not native token ITL. Source tokens are not measured DMA bytes. No quality-equivalence claim.',fontsize=10)
    Path('figures').mkdir(exist_ok=True)
    for ext in ['png','svg']:fig.savefig(f'figures/v6dev1_main_tradeoffs.{ext}',dpi=170,bbox_inches='tight')
    plt.close(fig)


if __name__=='__main__':main()
