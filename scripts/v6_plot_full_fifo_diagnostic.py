"""Single audited full baseline: backlog, sampled GPU/queue and source accounting."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from v6_raw_archive import expanded,sha

RID='v6full1-main-g6-fifo64-s901'
BASE=Path('results/v3');RAW=BASE/'raw'


def main():
    auditpath=BASE/(RID+'.full_audit_r1.json');a=json.loads(auditpath.read_text())
    assert a['complete'] and a['requests']==1986 and not a['errors']
    archivepath=BASE/(RID+'.archive_r1.json')
    with expanded(archivepath) as manifest:
        assert manifest['audit_sha256']==sha(auditpath)
        assert {r['path']:r['sha256'] for r in manifest['files']}==a['raw_sha256']
        requests=[json.loads(l) for l in (RAW/(RID+'.jsonl')).read_text().splitlines()]
        gateway=[json.loads(l) for l in (RAW/(RID+'.gateway.jsonl')).read_text().splitlines()]
        metrics=[json.loads(l) for l in (RAW/(RID+'.metrics.jsonl')).read_text().splitlines()]
    assert len(requests)==len(gateway)==1986
    assert {r['request_id'] for r in requests}=={r['request_id'] for r in gateway}
    t0=min(r['scheduled_arrival_ns'] for r in requests)
    colors=['#5575ad','#e1a23b','#3b9c89','#b75a70']
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(13,8.7),layout='constrained')
    ax=axes[0,0]
    series=[('Scheduled arrival',requests,'scheduled_arrival_ns'),('Gateway received',gateway,'received_ns'),('Client first text',requests,'first_token_ns'),('Client completed',requests,'complete_ns')]
    for (label,rows,key),color in zip(series,colors):
        values=sorted((r[key]-t0)/1e9 for r in rows)
        ax.step([0]+values,[0]+list(range(1,len(values)+1)),where='post',label=label,color=color,lw=1.7)
    ax.set(title='A. Offered arrivals and observed progress',xlabel='Seconds since first scheduled arrival',ylabel='Cumulative requests')
    ax.legend(fontsize=8,loc='lower right');ax.grid(alpha=.15)
    ax=axes[0,1];times=[(m['timestamp_ns']-t0)/1e9 for m in metrics]
    for key,label,color in [('vllm:num_requests_running','Running','#3b9c89'),('vllm:num_requests_waiting','Waiting','#b75a70')]:
        values=[m['vllm'].get(key) for m in metrics]
        assert all(v is not None for v in values),key
        ax.plot(times,values,label=label,color=color,lw=1)
    twin=ax.twinx();twin.plot(times,[m['gpu']['gpu_util_pct'] for m in metrics],color='#777777',alpha=.4,lw=.7,label='GPU utilization')
    twin.set(ylabel='GPU utilization (%)',ylim=(0,105));ax.set(title='B. Existing sampled engine queue / GPU',xlabel='Seconds since first scheduled arrival',ylabel='Requests')
    lines=ax.get_lines()+twin.get_lines();ax.legend(lines,[l.get_label() for l in lines],fontsize=8,loc='upper right');ax.grid(alpha=.15)
    ax=axes[1,0];stages=a['waits']['runs'][0]['stages_ms']
    keys=['arrival_to_gateway','gateway_prepare','gateway_admission','upstream_to_token','return_stream']
    labels=['Arrival → gateway','Gateway prepare','Admission wait','Upstream → first text','Return stream']
    means=[stages[k]['mean']/1000 for k in keys]
    ax.barh(labels,means,color=['#5575ad','#d1d9e9','#e1a23b','#3b9c89','#b75a70'])
    for i,v in enumerate(means):ax.text(v+4,i,f'{v:.3f} s',va='center',fontsize=9)
    ax.invert_yaxis();ax.set(xlim=(0,max(means)*1.3),title='C. Additive mean scheduled-arrival TTFT',xlabel=f'Seconds; sum = {sum(means):.3f} s (means only)');ax.grid(axis='x',alpha=.15)
    ax=axes[1,1];c=a['resource']['strict_counter_deltas']['vllm']
    counts=[c[k] for k in ['vllm:prompt_tokens_source_external_kv_transfer_total','vllm:prompt_tokens_source_local_cache_hit_total','vllm:request_prefill_kv_computed_tokens_sum']]
    total=c['vllm:prompt_tokens_total'];assert sum(counts)==total==50522325
    labels=['External KV consumed','GPU-local reuse','New prefill']
    ax.barh(labels,counts,color=['#5575ad','#3b9c89','#e1a23b']);ax.set_xscale('log')
    for i,v in enumerate(counts):ax.text(v*1.12,i,f'{int(v):,}\n({v/total:.2%})',va='center',fontsize=9)
    ax.invert_yaxis();ax.set(xlim=(1e5,3e8),title='D. Engine-labelled prompt-token sources',xlabel='Tokens (log scale); not physical DMA bytes');ax.grid(axis='x',alpha=.15)
    fig.suptitle('Full FIFO baseline, seed901: 1,986 successful requests\nOne audited arm; no full candidate comparison',fontsize=15)
    fig.text(.01,-.025,'Connection cap256; arrival→ingress delay is not fully attributed. Upstream includes engine queue/copy/compute/transport.\nGPU samples do not separate DMA and compute. Warmup60 is excluded. No stage-quantile addition or throughput-capacity claim.',fontsize=9)
    paths=[]
    for ext in ['png','svg']:
        path=Path('figures')/('v6full1_fifo_diagnostic.'+ext);fig.savefig(path,dpi=160,bbox_inches='tight');paths.append(path)
    plt.close(fig)
    report=dict(run_id=RID,complete_single_arm=True,full_study_complete=False,audit_sha256=sha(auditpath),archive_sha256=sha(archivepath),
        source_sha256=sha(__file__),raw_sha256=a['raw_sha256'],mean_stages_seconds=dict(zip(keys,means)),source_tokens=dict(zip(labels,counts)),
        figure_sha256={str(p):sha(p) for p in paths},scope='Single full FIFO baseline; original sampled metrics and client/gateway timestamps. No candidate gain, root-cause attribution, exact DMA measurement, quality equivalence or completed study.')
    (BASE/'v6full1_fifo_diagnostic_plot.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Rendered single-arm diagnostic',flush=True)


if __name__=='__main__':main()
