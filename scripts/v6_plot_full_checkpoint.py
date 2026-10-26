"""Plot one full arrival seed from an explicit audited-prefix checkpoint."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from v6_raw_archive import sha


def main():
    p=argparse.ArgumentParser();p.add_argument('checkpoint',type=Path);p.add_argument('--output-prefix',type=Path,required=True);a=p.parse_args()
    report=json.loads(a.checkpoint.read_text());assert report['kind']=='interim_full_checkpoint_not_terminal_audit' and report['complete'] is False
    runs=[r for r in report['runs'] if r['step']['engine']=='main' and r['step']['seed']==901 and r['step']['budget']==6]
    assert len(runs)>=2 and all(r['summary']['requests']==r['summary']['successes']==1986 and r['summary']['errors']==0 for r in runs)
    names=[r['step']['arm'] for r in runs];x=np.arange(len(runs));width=.24
    outputs=[Path(str(a.output_prefix)+'.'+ext) for ext in ['png','svg','json']]
    assert not any(p.exists() for p in outputs),'Preserve prior checkpoint plots'
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,3,figsize=(16,9),layout='constrained')
    ax=axes[0,0]
    for i,(q,color) in enumerate(zip(['p50_ms','p95_ms','p99_ms'],['#8ca4ca','#5575ad','#233f6c'])):
        ax.bar(x+(i-1)*width,[r['summary']['arrival_ttft_'+q]/1000 for r in runs],width,label=q.replace('_ms',''),color=color)
    ax.set(title='A. Scheduled-arrival TTFT',ylabel='Seconds');ax.set_xticks(x,names);ax.legend();ax.grid(axis='y',alpha=.15)
    ax=axes[0,1];bottom=np.zeros(len(runs));source_counts={}
    for key,label,color in [('vllm:request_prefill_kv_computed_tokens_sum','New prefill','#e1a23b'),('vllm:prompt_tokens_source_local_cache_hit_total','GPU local','#3b9c89'),('vllm:prompt_tokens_source_external_kv_transfer_total','External consumed','#5575ad')]:
        vals=np.array([r['resource']['strict_counter_deltas']['vllm'][key] for r in runs]);source_counts[label]=vals.tolist()
        percentages=vals/50522325*100;ax.bar(x,percentages,bottom=bottom,label=label,color=color);bottom+=percentages
    assert np.allclose(bottom,100);ax.set(title='B. Prompt-token source proportions',ylabel='% of 50,522,325 prompt tokens',ylim=(0,108));ax.set_xticks(x,names);ax.legend(fontsize=8,loc='lower right')
    ax=axes[0,2];bottom=np.zeros(len(runs))
    keys=['arrival_to_gateway','gateway_prepare','gateway_admission','upstream_to_token','return_stream']
    for key,label,color in zip(keys,['Arrival → gateway','Prepare','Admission','Upstream → text','Return'],['#5575ad','#d2d9e5','#e1a23b','#3b9c89','#b75a70']):
        vals=np.array([r['waits']['runs'][0]['stages_ms'][key]['mean']/1000 for r in runs]);ax.bar(x,vals,bottom=bottom,label=label,color=color);bottom+=vals
    ax.set(title='C. Additive mean TTFT stages',ylabel='Seconds (mean; quantiles do not add)');ax.set_xticks(x,names);ax.legend(fontsize=8);ax.grid(axis='y',alpha=.15)
    ax=axes[1,0]
    for i,r in enumerate(runs):
        h=r['native_itl'];assert h['coverage_valid'];bounds=h['quantile_bounds']['p95'];assert not bounds['upper_unbounded']
        ax.plot([i-.18,i-.18],[bounds['lower_ms'],bounds['upper_ms']],color='#5575ad',lw=9,alpha=.5,label='Native update p95 bucket' if i==0 else None)
        ax.scatter(i,h['native_itl_mean_ms'],color='#233f6c',s=45,label='Native update mean' if i==0 else None)
        ax.scatter(i+.18,r['secondary']['client_tpot_proxy_ms']['p95'],color='#b75a70',marker='D',s=40,label='Client TPOT proxy p95' if i==0 else None)
    ax.set(title='D. Decode cost: distinct measurement units',ylabel='Milliseconds; bucket range is not a CI');ax.set_xticks(x,names);ax.legend(fontsize=8,loc='upper left');ax.grid(axis='y',alpha=.15)
    ax=axes[1,1];categories=['1','2','3','4','5'];xx=np.arange(5);bw=.7/len(runs)
    for i,r in enumerate(runs):ax.bar(xx+(i-(len(runs)-1)/2)*bw,[r['quality']['by_category'][c]['mean'] for c in categories],bw,label=names[i])
    ax.set_xticks(xx,['C1 F1','C2 F1','C3 F1','C4 F1','C5 accuracy']);ax.set(title='E. Official quality by category',ylabel='Score (same 1,986 QA)',ylim=(0,1));ax.legend(fontsize=8);ax.grid(axis='y',alpha=.15)
    ax=axes[1,2];base={r['sample_id']:r for r in runs[0]['per_conversation']};samples=sorted(base);xx=np.arange(len(samples));bw=.7/(len(runs)-1)
    for i,r in enumerate(runs[1:]):
        current={r['sample_id']:r for r in r['per_conversation']};assert current.keys()==base.keys()
        vals=[100*(current[k]['arrival_ttft_ms']['p95']/base[k]['arrival_ttft_ms']['p95']-1) for k in samples]
        ax.bar(xx+(i-(len(runs)-2)/2)*bw,vals,bw,label=r['step']['arm'])
    ax.set_xticks(xx,[k.replace('conv-','') for k in samples]);ax.axhline(0,color='#555555',lw=.7);ax.set(title='F. Per-conversation p95 versus FIFO',ylabel='Change (%)',xlabel='Conversation ID');ax.legend(fontsize=8);ax.grid(axis='y',alpha=.15)
    fig.suptitle(f'Full main stack, seed901: {len(runs)} audited arms, 1,986 QA each\nInterim single-seed evidence; remaining full study incomplete',fontsize=16)
    fig.text(.01,-.025,'Distinct fresh engines/LMCache; 60 warmups per arm excluded. B shows source tokens, not DMA bytes. D compares engine output-update\nhistograms with a request-level client proxy; neither is exact per-token ITL. No run-level CI or quality-equivalence claim from one seed.',fontsize=10)
    for path in outputs[:2]:fig.savefig(path,dpi=160,bbox_inches='tight')
    plt.close(fig)
    proof=dict(checkpoint_path=str(a.checkpoint),checkpoint_sha256=sha(a.checkpoint),source_sha256=sha(__file__),runs=[r['run_id'] for r in runs],
        complete_study=False,arrival_seed=901,source_counts=source_counts,figure_sha256={str(p):sha(p) for p in outputs[:2]},
        scope='Audited full single-seed main-stack subset, all QA and category scores; descriptive intervals only where native histogram buckets identify a range. No incomplete-arm quantiles, model calls, terminal-study claim or quality equivalence.')
    with outputs[2].open('x') as output:output.write(json.dumps(proof,indent=2)+'\n')
    print('Rendered checkpoint',len(runs),'arms',flush=True)


if __name__=='__main__':main()
