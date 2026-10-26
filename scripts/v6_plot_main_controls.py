"""Plot p50 and p95 only after the complete main 36-arm audit exists."""
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    source=Path('results/v3/v6controls1_main_audit.json');blob=source.read_bytes();audit=json.loads(blob)
    assert audit['complete'] and audit['errors']==0 and audit['requests']==1260 and len(audit['runs'])==36
    assert audit['separate_warmup_requests']==2160
    regimes=[('lowload','Lower load: 2 QPS, 60 QA, 6 GiB'),('lowreuse','Low reuse: 8 QA, 6 GiB'),
             ('gpufit','GPU fit: 60 QA, 10 GiB'),('abstention','Abstention: 12 QA, 6 GiB')]
    fig,axes=plt.subplots(4,2,figsize=(10,12))
    fig.subplots_adjust(hspace=.5,wspace=.35,bottom=.15,top=.94)
    for row,(regime,title) in enumerate(regimes):
        for col,(metric,label) in enumerate([('p50_ms','Median'),('p95_ms','p95')]):
            ax=axes[row,col]
            for x,candidate in enumerate(['union64','packing_ready']):
                pairs=[p for p in audit['pairs'] if p['regime']==regime and p['baseline']=='fifo64' and p['candidate']==candidate]
                assert sorted(p['seed'] for p in pairs)==[101,102,103]
                for offset,pair,marker in zip([-.08,0,.08],sorted(pairs,key=lambda p:p['seed']),['o','s','^']):
                    ax.scatter(x+offset,pair[metric+'_delta_pct'],marker=marker,s=40,
                        color=['#378469','#2b73a4'][x],label=str(pair['seed']) if x==0 else None,zorder=3)
            ax.axhline(0,color='black',lw=.8)
            if regime=='lowreuse' and metric=='p95_ms':
                ax.axhline(5,color='#a54444',ls='--',lw=1);ax.set_ylim(-1,6)
                ax.text(.02,.9,'5% p95 gate',transform=ax.transAxes,color='#a54444',fontsize=8)
            ax.set_xticks([0,1],['Old union','Ready union']);ax.set_xlim(-.4,1.4)
            ax.set_title(f'{title}: {label}',fontsize=9)
            ax.set_ylabel(f'TTFT {label} change vs FIFO64 (%)',fontsize=9)
            ax.spines[['right','top']].set_visible(False);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    axes[0,0].legend(title='Arrival seed',frameon=False,fontsize=8,title_fontsize=8,loc='upper right')
    fig.suptitle('Main controls: scheduled-arrival TTFT median and tail changes',fontsize=13)
    fig.text(.06,.035,'36 fresh engine/LMCache arms; 1,260 measured responses and 2,160 separate warmups.\nDots are matched per-seed contrasts on exposed QA; negative means lower latency.\nOnly low reuse has the declared 5% gate. Repeated schedules do not add independent semantic examples.\nLatency panels do not establish quality equivalence; scores, cap hits and work counters remain in the audit.\nThis is the complete development-control stage, not the full 1,986-QA serving study.',fontsize=9)
    Path('figures').mkdir(exist_ok=True)
    outputs=[Path(f'figures/v6controls1_main.{ext}') for ext in ['png','svg']]
    for path in outputs:fig.savefig(path,dpi=170,bbox_inches='tight')
    plt.close(fig)
    svg=outputs[1];svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    digest=hashlib.sha256(blob).hexdigest();assert sha(source)==digest
    proof=dict(source_audit_sha256=digest,analysis_source_sha256=sha(__file__),matplotlib_version=matplotlib.__version__,
        figures_sha256={str(p):sha(p) for p in outputs},scope='Complete36-arm main controls only; no new inference, quality-equivalence or full-study claim.')
    Path('results/v3/v6controls1_main_plot.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':main()
