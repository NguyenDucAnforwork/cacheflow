"""Render the complete15-arm native primary subset, not the60-arm study."""
import json
import statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    p=json.loads(Path('results/v3/sglang/v6native1_primary_audit.json').read_text())
    assert p['primary_complete'] and not p['overall_native_stage_complete'] and p['requests']==900 and len(p['runs'])==15
    oracle=json.loads(Path('results/v3/v6dev1_input_oracle.json').read_text())['page16']['input_only_minimum_new_tokens']
    arms=['native','fifo64','union64','ready_fifo','packing_ready'];names=['Native LPM','FIFO64','Union64','Ready FIFO','Ready union']
    colors=['#89929b','#89929b','#378469','#8d75ac','#2b73a4'];by={r['arm']:r for r in p['aggregate']};x=np.arange(5)
    fig,axs=plt.subplots(2,2,figsize=(11,8));fig.subplots_adjust(bottom=.16,hspace=.38,wspace=.3)
    ax=axs[0,0]
    ax.bar(x-.17,[by[a]['p50_ms']/1000 for a in arms],width=.34,color=colors,alpha=.4,label='p50')
    ax.bar(x+.17,[by[a]['p95_ms']/1000 for a in arms],width=.34,color=colors,label='p95')
    for i,a in enumerate(arms):ax.scatter([i+.17]*3,[r['p95_ms']/1000 for r in p['runs'] if r['arm']==a],s=13,c='black',zorder=3)
    ax.set_title('A. Scheduled-arrival TTFT');ax.set_ylabel('Seconds');ax.legend(frameon=False,fontsize=9)
    ax=axs[0,1];ax.bar(x,[by[a]['computed_tokens']/1000 for a in arms],color=colors)
    ax.axhline(oracle/1000,c='black',ls='--',lw=1,label=f'Input-only reference: {oracle:,} tokens')
    ax.set_ylim(0,82);ax.set_title('B. Native new-prefill source tokens');ax.set_ylabel('Thousand tokens');ax.legend(frameon=False,fontsize=9)
    ax=axs[1,0];ax.bar(x,[by[a]['completion_p95_ms']/1000 for a in arms],color=colors)
    for i,a in enumerate(arms):ax.scatter([i]*3,[r['secondary']['completion_latency_ms']['p95']/1000 for r in p['runs'] if r['arm']==a],s=13,c='black',zorder=3)
    ax.set_title('C. Response completion p95');ax.set_ylabel('Seconds')
    ax=axs[1,1];baseline={s:next(r['f1'] for r in p['runs'] if r['run_id']==f'v6native1-primary-s{s}-native') for s in [101,102,103]}
    for i,a in enumerate(arms):
        values=[100*(next(r['f1'] for r in p['runs'] if r['run_id']==f'v6native1-primary-s{s}-{a}')-baseline[s]) for s in [101,102,103]]
        ax.scatter([i-.08,i,i+.08],values,c=colors[i],s=35,zorder=3)
    ax.axhline(0,c='black',lw=1);ax.set_title('D. F1 changes versus native, by seed');ax.set_ylabel('Absolute percentage points')
    for ax in axs.flat:
        ax.set_xticks(x,names,rotation=23,ha='right',fontsize=9);ax.spines[['right','top']].set_visible(False);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('Native primary development: less prefill is not sufficient for lower latency',fontsize=14)
    fig.text(.06,.035,'60 exposed QA, three fresh native blocks, five arms per block after flush/fresh gateway. Bars: means of run quantiles/counts.\nStatic input-only reference assumes full retention and immediate publication; no queue/IO/decoder model.\nSource tokens are not FLOPs or DMA time. Quality changes are descriptive; overall 60-arm study remains incomplete.',fontsize=9)
    for ext in ['png','svg']:fig.savefig(f'figures/v6native1_primary_tradeoffs.{ext}',dpi=170,bbox_inches='tight')
    plt.close(fig)


if __name__=='__main__':main()
