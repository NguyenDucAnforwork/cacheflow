"""Full native seed901 tradeoffs, exact completed five-arm subset only."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from v6_raw_archive import sha


def plot(source,stem):
    source=Path(source);stem=Path(stem);cp=json.loads(source.read_text())
    assert cp['kind']=='interim_full_checkpoint_not_terminal_audit'
    arms=['native_lpm','native_dfs','fifo64','union64','packing_ready']
    by={r['step']['arm']:r for r in cp['runs'] if r['step']['engine']=='sg' and r['step']['budget']==6 and r['step']['seed']==901}
    assert set(by)==set(arms);runs=[by[a] for a in arms];labels=['Native LPM','Native DFS','Gateway FIFO','Union','Ready union'];x=np.arange(5)
    costs=[];provenance={}
    for r in runs:
        rid=r['run_id'];ap=Path(f'results/v3/{rid}.full_audit_r1.json');sp=Path(f'results/v3/sglang/{rid}.setup.json');a=json.loads(ap.read_text())
        assert sha(ap)==r['audit_sha256'] and sha(sp)==a['setup_sha256'];provenance[rid]=dict(audit_sha256=sha(ap),setup_sha256=sha(sp))
        setup=json.loads(sp.read_text());before=(setup.get('gateway_before') or {}).get('decision_stats');after=(setup.get('gateway_after') or {}).get('decision_stats')
        if after is None:costs.append(None)
        else:
            assert before['calls']==before['cache_hits']==before['cpu_ms']==0
            costs.append(after['cpu_ms']/1000)
    assert costs[:3]==[None]*3 and all(c is not None for c in costs[3:])
    for suffix in ['.png','.svg','.json']:assert not stem.with_suffix(suffix).exists()
    fig,axes=plt.subplots(3,2,figsize=(14,12));colors=['#397ca7','#da8e2d','#6a795f','#6d60a8','#b64e62']
    for i,q in enumerate(['p50','p95','p99']):
        values=[r['summary']['arrival_ttft_'+q+'_ms']/1000 for r in runs]
        bars=axes[0,0].bar(x+(i-1)*.25,values,width=.23,label=q.upper());axes[0,0].bar_label(bars,labels=[f'{v:.1f}' for v in values],padding=3,fontsize=7)
    axes[0,0].set_yscale('log');axes[0,0].set_ylim(3,2000);axes[0,0].set_ylabel('Scheduled-arrival TTFT (s, log scale)');axes[0,0].legend(ncol=3,fontsize=8)
    values=[r['resource']['counter_deltas']['sglang:uncached_prompt_tokens_histogram_sum']/1000 for r in runs]
    bars=axes[0,1].bar(x,values,color=colors);axes[0,1].bar_label(bars,fmt='%.3f',fontsize=8,padding=3);axes[0,1].set_ylim(0,375)
    axes[0,1].axhline(304.885,color='#333',linestyle='--',label='Input-only full-retention reference');axes[0,1].set_ylabel('New prefill (thousand tokens)');axes[0,1].legend(fontsize=8,loc='lower left')
    values=[r['quality']['answerable_f1'] for r in runs]
    bars=axes[1,0].bar(x,values,color=colors);axes[1,0].bar_label(bars,fmt='%.6f',fontsize=8,padding=3);axes[1,0].set_ylim(0,.37);axes[1,0].set_ylabel('Official answerable F1 (1,540 QA)')
    for i,r in enumerate(runs):axes[1,0].text(i,.08,f"Cat5: {round(r['quality']['by_category']['5']['mean']*446)}/446\nCap: {r['quality']['output_budget_hits']}",ha='center',fontsize=8,color='white')
    values=[r['native_itl']['native_itl_mean_ms'] for r in runs]
    bars=axes[1,1].bar(x,values,color=colors);axes[1,1].bar_label(bars,fmt='%.2f',padding=3,fontsize=8);axes[1,1].set_ylim(0,40);axes[1,1].set_ylabel('Native update-interval mean (ms)')
    for i,r in enumerate(runs):
        b=r['native_itl']['quantile_bounds']['p95'];axes[1,1].text(i,3,f"p95 bucket\n{b['lower_ms']:g}–{b['upper_ms']:g} ms",ha='center',fontsize=8,color='white')
    axes[2,0].bar([0,1],costs[3:],color=colors[3:]);axes[2,0].set_xticks([0,1],labels[3:]);axes[2,0].set_ylim(0,340);axes[2,0].set_ylabel('Chooser thread CPU (s, hits + misses)')
    for i,c in enumerate(costs[3:]):axes[2,0].text(i,c+8,f'{c:.3f}',ha='center')
    axes[2,0].text(.5,10,'Other three baselines: missing counters, not zero',ha='center',fontsize=9)
    gx=np.arange(3);bottom=np.zeros(3)
    stages=[('arrival_to_gateway','Arrival→gateway','#8097b0'),('gateway_prepare','Preparation','#d6ae63'),('gateway_admission','Admission','#8f83af'),('upstream_to_token','Upstream→text','#6f9a7d'),('return_stream','Return','#b77d82')]
    for stage,label,color in stages:
        values=np.array([r['waits']['runs'][0]['stages_ms'][stage]['mean']/1000 for r in runs[2:]])
        axes[2,1].bar(gx,values,bottom=bottom,color=color,label=label);bottom+=values
    for i,v in enumerate(bottom):axes[2,1].text(i,v+5,f'{v:.3f}',ha='center',fontsize=8)
    axes[2,1].set_ylim(0,300);axes[2,1].set_xticks(gx,labels[2:]);axes[2,1].set_ylabel('Mean TTFT stages (s, gateway arms only)');axes[2,1].legend(ncol=2,fontsize=8,loc='upper right')
    for ax in axes[:2].flat:ax.set_xticks(x,labels,fontsize=8)
    for ax in axes.flat:ax.grid(axis='y',alpha=.17);ax.set_axisbelow(True)
    fig.suptitle('Full native seed901: compute savings do not guarantee end-to-end gains\n1,986 QA per arm · five fresh engines · full30-arm study incomplete',fontsize=14)
    fig.text(.5,.02,'Union vs DFS: p95 −7.76%, median +302.00%; four conversation p95 regressions. Ready union regresses versus both.\nCPU counters exclude timeout/HTTP/other gateway work; no causal CPU-to-wall subtraction. Missing promotion deltas remain null.',ha='center',fontsize=10)
    fig.tight_layout(rect=[0,.07,1,.94]);stem.parent.mkdir(parents=True,exist_ok=True)
    for suffix in ['.png','.svg']:fig.savefig(stem.with_suffix(suffix),dpi=160)
    plt.close(fig)
    with stem.with_suffix('.json').open('x') as out:out.write(json.dumps(dict(checkpoint=str(source),checkpoint_sha256=sha(source),plot_source_sha256=sha(__file__),
        audit_setup_sha256=provenance,figure_sha256={str(stem.with_suffix(s)):sha(stem.with_suffix(s)) for s in ['.png','.svg']},
        scope='Exact completed native five-arm seed901 subset, no three-seed interval, candidate universal win or quality equivalence. CPU is chooser-only; other baselines null. Stage means add, quantiles do not. Reference assumes full retention, not finite-cache optimality.'),indent=2)+'\n')
    print('Rendered full native checkpoint',stem,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--stem',type=Path,required=True);a=p.parse_args();plot(a.source,a.stem)
