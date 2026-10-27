"""Standalone full native baseline diagnostic, one seed; no candidate claim."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from v6_raw_archive import sha


def plot(source,stem):
    source=Path(source);stem=Path(stem);p=json.loads(source.read_text())
    assert p['kind']=='supplemental_full_native_baseline_diagnostic' and p['seed']==901
    for suffix in ['.png','.svg','.json']:assert not stem.with_suffix(suffix).exists()
    runs=p['runs'];labels=['Native LPM','Native DFS-weight','Gateway FIFO64'];x=np.arange(3)
    assert [r['arm'] for r in runs]==['native_lpm','native_dfs','fifo64']
    colors=['#3875a4','#d0832c','#64745e'];fig,axes=plt.subplots(2,2,figsize=(12,8.5))
    for i,q in enumerate(['p50','p95','p99']):
        values=[r['ttft_s'][q] for r in runs]
        bars=axes[0,0].bar(x+(i-1)*.25,values,width=.23,label=q.upper())
        axes[0,0].bar_label(bars,labels=[f'{v:.1f}' for v in values],padding=3,fontsize=8)
    axes[0,0].set_yscale('log');axes[0,0].set_ylim(3,1900);axes[0,0].set_ylabel('Scheduled-arrival TTFT (s, log scale)');axes[0,0].legend(ncol=3,fontsize=8)
    values=[r['new_prefill_tokens']/1000 for r in runs]
    bars=axes[0,1].bar(x,values,color=colors);axes[0,1].bar_label(bars,fmt='%.1f',padding=3)
    axes[0,1].axhline(304.885,color='#333333',linestyle='--',label='Input-only full-retention reference')
    axes[0,1].set_ylim(0,375);axes[0,1].set_ylabel('New prefill (thousand tokens)');axes[0,1].legend(fontsize=8,loc='lower left')
    values=[r['answerable_f1'] for r in runs]
    bars=axes[1,0].bar(x,values,color=colors);axes[1,0].bar_label(bars,fmt='%.6f',padding=3,fontsize=8)
    axes[1,0].set_ylim(0,.37);axes[1,0].set_ylabel('Official answerable F1 (1,540 QA)')
    for i,r in enumerate(runs):axes[1,0].text(i,.08,f"Category 5: {r['category5_correct']}/446\nCap hits: {r['output_budget_hits']}",ha='center',fontsize=8,color='white')
    values=[r['native_itl']['native_itl_mean_ms'] for r in runs]
    bars=axes[1,1].bar(x,values,color=colors);axes[1,1].bar_label(bars,fmt='%.2f',padding=3)
    axes[1,1].set_ylim(0,40);axes[1,1].set_ylabel('Native update-interval mean (ms)')
    for ax in axes.flat:
        ax.set_xticks(x,labels,fontsize=9);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    fig.suptitle('Full LoCoMo: strong native baselines change the conclusion\nSeed 901 only · 1,986 QA per arm · fresh engine per arm · study incomplete',fontsize=13)
    fig.text(.5,.025,'Supplemental baseline contrasts, not a method win. Native LPM/DFS use direct admission; FIFO uses a gateway.\nReference assumes full retention; ITL is an engine-update metric. Missing promotion deltas remain null. No exact Strata reproduction.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.075,1,.91]);stem.parent.mkdir(parents=True,exist_ok=True)
    for suffix in ['.png','.svg']:fig.savefig(stem.with_suffix(suffix),dpi=170)
    plt.close(fig)
    with stem.with_suffix('.json').open('x') as out:out.write(json.dumps(dict(source=str(source),source_sha256=sha(source),plot_source_sha256=sha(__file__),
        figure_sha256={str(stem.with_suffix(s)):sha(stem.with_suffix(s)) for s in ['.png','.svg']},scope=p['scope']),indent=2)+'\n')
    print('Rendered',stem,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--stem',type=Path,required=True);a=p.parse_args();plot(a.source,a.stem)
