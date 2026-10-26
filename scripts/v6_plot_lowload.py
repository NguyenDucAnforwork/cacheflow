"""Plot complete low-load subsets, with separate within-stack references."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    panels=[('Main: vLLM / LMCache',Path('results/v3/v6controls1_main_lowload_subset_audit.json'),'fifo64'),
            ('Native: SGLang / HiCache',Path('results/v3/sglang/v6native1_lowload_subset_audit.json'),'native')]
    fig,axes=plt.subplots(2,2,figsize=(10,7))
    fig.subplots_adjust(bottom=.22,hspace=.45,wspace=.35)
    for row,(title,path,baseline) in enumerate(panels):
        audit=json.loads(path.read_text())
        assert audit['subset_complete'] and audit['requests']==540 and audit['errors']==0 and len(audit['runs'])==9
        for col,(metric,label) in enumerate([('p95_ms','p95'),('p50_ms','Median')]):
            ax=axes[row,col]
            for x,candidate in enumerate(['union64','packing_ready']):
                pairs=[p for p in audit['pairs'] if p['baseline']==baseline and p['candidate']==candidate]
                assert sorted(p['seed'] for p in pairs)==[101,102,103]
                for offset,pair,marker in zip([-.08,0,.08],sorted(pairs,key=lambda p:p['seed']),['o','s','^']):
                    ax.scatter(x+offset,pair[metric+'_delta_pct'],marker=marker,s=45,
                               color=['#378469','#2b73a4'][x],label=str(pair['seed']) if x==0 else None,zorder=3)
            ax.axhline(0,color='black',lw=.8)
            ax.set_xticks([0,1],['Old union','Ready union']);ax.set_xlim(-.4,1.4)
            ax.set_title(f'{title}: {label}',fontsize=10)
            ax.set_ylabel(f'{label} TTFT change vs {baseline} (%)')
            ax.spines[['right','top']].set_visible(False);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    axes[0,0].legend(title='Arrival seed',frameon=False,fontsize=8,title_fontsize=8,loc='upper right')
    fig.suptitle('At 2 QPS, admission effects depend on the serving stack',fontsize=13)
    fig.text(.06,.045,'Each panel compares matched arms within its own stack; negative means lower latency.\n60 exposed QA, three arrival schedules; dots are individual seed contrasts, not independent semantic samples.\nMain: fresh engine per arm. Native: fresh engine per seed, flushed between arms.\nThese are separate protocols, not a causal cross-engine timing comparison. Quality and decode costs remain in the audits.',fontsize=9)
    for ext in ['png','svg']:fig.savefig(f'figures/v6_lowload_tradeoffs.{ext}',dpi=170,bbox_inches='tight')
    svg=Path('figures/v6_lowload_tradeoffs.svg')
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)


if __name__=='__main__':main()
