"""All45 registered synthetic CPU cases, no selected E2E speedup claim."""
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np


def main():
    source=Path('results/v3/v7_epoch_cpu_probe_registration.result.json');r=json.loads(source.read_text())
    assert r['complete'] and r['synthetic'] and not r['gpu_execution'] and len(r['cases'])==45
    policies=['packing_reuse','packing_ready','ready_fifo'];kernels=['chooser_hit','timeout_hit','poll_mutating'];queues=[16,64,128,256,512]
    cells={(c['policy'],c['kernel'],c['queue']):c for c in r['cases']};assert len(cells)==45
    assert set(cells)=={(p,k,q) for p in policies for k in kernels for q in queues}
    rows=[]
    for (p,k,q),c in cells.items():
        assert len(c['samples']['legacy'])==len(c['samples']['prototype'])==5
        old=c['median_thread_cpu_ns_per_iteration']['legacy'];new=c['median_thread_cpu_ns_per_iteration']['prototype']
        assert old>0 and new>0 and c['legacy_over_prototype_cpu_ratio']==old/new
        rows.append(dict(policy=p,kernel=k,queue=q,legacy_us=old/1000,epoch_us=new/1000,ratio=old/new))
    fig,axes=plt.subplots(1,3,figsize=(12,3.5),sharey=True)
    titles=['Chooser: unchanged state','Timeout: unchanged state','Polls with mutation']
    for ax,k,title in zip(axes,kernels,titles):
        data=np.array([[cells[p,k,q]['legacy_over_prototype_cpu_ratio'] for q in queues] for p in policies])
        im=ax.imshow(data,norm=LogNorm(vmin=1,vmax=32),cmap='YlGnBu',aspect='auto')
        for i in range(3):
            for j in range(5):ax.text(j,i,f'{data[i,j]:.2f}',ha='center',va='center',fontsize=9,color='white' if data[i,j]>=8 else '#17212b')
        ax.set_xticks(range(5),queues);ax.set_yticks(range(3),['Union','Ready union','Ready FIFO']);ax.set_xlabel('Queued requests');ax.set_title(title,fontsize=11)
    fig.subplots_adjust(left=.10,right=.90,bottom=.22,top=.77,wspace=.17)
    cax=fig.add_axes([.92,.26,.015,.48]);cb=fig.colorbar(im,cax=cax,ticks=[1,2,4,8,16,32]);cb.ax.set_yticklabels(['1','2','4','8','16','32']);cb.set_label('Legacy / epoch CPU ratio')
    fig.suptitle('Synthetic scheduler CPU kernels: all 45 registered cases',fontsize=14,y=.97)
    fig.text(.10,.86,'Median thread CPU per iteration • 5 alternating rounds × 2,000 iterations',fontsize=10)
    fig.text(.10,.07,'Blocked fixture: 4 active requests, 1,024-token shared prefix. No GPU or end-to-end speedup claim.',fontsize=9)
    out=Path('figures/v7_epoch_cpu_all45');out.parent.mkdir(exist_ok=True)
    paths=[out.with_suffix('.png'),out.with_suffix('.svg')]
    assert all(not p.exists() for p in paths)
    for p in paths:fig.savefig(p,dpi=170,facecolor='white')
    plt.close(fig)
    metadata=dict(input_path=str(source),input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        plot_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cells=sorted(rows,key=lambda r:(r['kernel'],r['policy'],r['queue'])),
        figure_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        scope='All45synthetic registered CPU cases; ratios of per-implementation medians, not E2E speedups, uncertainty intervals, DMA or GPU performance.')
    path=Path('results/v3/v7_epoch_cpu_all45_figure.json');assert not path.exists();path.write_text(json.dumps(metadata,indent=2)+'\n')
    print('Rendered all45synthetic CPU cases with source hashes')


if __name__=='__main__':main()
