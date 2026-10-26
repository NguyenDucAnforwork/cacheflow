"""Plot audited complete three-seed controls only; not a full-study result."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    regimes=['dfs','lowload','lowreuse','gpufit'];titles=['Native DFS, 6 GiB, 4 QPS','Native LPM, 6 GiB, 2 QPS','Low reuse, 8 QA, 6 GiB','GPU fit, 60 QA, 10 GiB']
    fig,axs=plt.subplots(2,2,figsize=(10,7.2));fig.subplots_adjust(hspace=.38,wspace=.25,bottom=.17)
    markers=['o','s','^'];colors=['#478d6b','#2d71a1']
    for ax,regime,title in zip(axs.flat,regimes,titles):
        a=json.loads(Path(f'results/v3/sglang/v6native1_{regime}_subset_audit.json').read_text());assert a['subset_complete'] and a['errors']==0 and len(a['runs'])==9
        for i,candidate in enumerate(['union64','packing_ready']):
            for j,seed in enumerate([101,102,103]):
                pair=next(p for p in a['pairs'] if p['baseline']=='native' and p['candidate']==candidate and p['seed']==seed)
                ax.scatter(i+(j-1)*.08,pair['p95_ms_delta_pct'],marker=markers[j],s=45,color=colors[i],label=f'Seed{seed}' if i==0 else None,zorder=3)
        ax.axhline(0,color='black',lw=.8)
        if regime=='lowreuse':ax.axhline(5,color='#aa4444',ls='--',lw=1);ax.set_ylim(-1,6);ax.text(.02,.9,'5% gate',transform=ax.transAxes,color='#aa4444',fontsize=9)
        ax.set_xticks([0,1],['Old union','Ready union']);ax.set_xlim(-.4,1.4);ax.set_ylabel('TTFT p95 change vs native (%)');ax.set_title(title,fontsize=11)
        ax.spines[['right','top']].set_visible(False);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    axs[0,0].legend(frameon=False,fontsize=8,loc='upper right')
    fig.suptitle('Native controls: tail gains depend on regime; low reuse stays within gate',fontsize=13)
    fig.text(.06,.04,'Dots are matched per-seed contrasts, three fresh engine blocks per regime; exposed QA repeated across schedules.\nOnly low reuse has the declared 5% gate. Negative is lower p95. Median/quality costs are retained in audits and report.\nThese four controls are complete; the overall 60-arm stage and full 1,986-QA study remain separate.',fontsize=9)
    for ext in ['png','svg']:fig.savefig(f'figures/v6native1_controls.{ext}',dpi=170,bbox_inches='tight')
    plt.close(fig)


if __name__=='__main__':main()
