"""Render audited physical vs logical prefix allocation, not transfer timing."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    audit=json.loads(Path('results/v3/v5diag_stall1_complete_audit.json').read_text())
    assert audit['requests']==660 and not audit['errors']
    s=audit['peak_duplicate_snapshot'];requests=s['requests'];assert len(requests)==4
    remote=[r for r in requests if r['status']=='WAITING_FOR_REMOTE_KVS'];assert len(remote)==2
    logical=remote[0]['block_tables'][0]['blocks'];physical=s['tracked_request_unique_physical_blocks']
    assert logical==1776 and physical==2696 and s['free_blocks']==33
    per_block=16*147456/(1<<30)
    rows=[]
    for name in audit['native_journal_sha256']:
        rows.extend(json.loads(l) for l in Path(name).read_text().splitlines())
    selected=[r for r in rows if r['kind']=='scheduler' and any('v5diag-stall1-on-history-bundle' in q['request_id'] for q in r['requests'])]
    selected.sort(key=lambda r:r['monotonic_ns']);t0=selected[0]['monotonic_ns']
    x=[(r['monotonic_ns']-t0)/1e9 for r in selected]
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.6),layout='constrained')
    axes[0].bar(['One logical\nprefix copy','Actual allocated\nphysical blocks'],[logical*per_block,physical*per_block],color=['#4477aa','#cc6677'],width=.6)
    axes[0].axhline((s['total_blocks']-1)*per_block,c='black',ls='--',lw=1,label='Usable GPU block pool')
    for i,n in enumerate([logical,physical]):axes[0].text(i,n*per_block+.07,f'{n*per_block:.3f} GiB',ha='center')
    axes[0].set_ylim(0,6.7);axes[0].set_ylabel('Allocated KV payload (GiB)');axes[0].legend(fontsize=8)
    axes[0].set_title('Two pending restores: 2.021 GiB extra allocation')
    axes[1].plot(x,[r['duplicate_physical_blocks_above_one_per_expected_hash'] for r in selected],'o-',c='#cc6677',label='Duplicate prefix allocations')
    axes[1].plot(x,[r['free_blocks'] for r in selected],'s-',c='#4477aa',label='Free physical blocks')
    axes[1].set_xlabel('Seconds from first bundle snapshot');axes[1].set_ylabel('Blocks (16 tokens each)')
    axes[1].set_title('Two-second point samples; transient peak recovered');axes[1].legend(fontsize=8)
    for ax in axes:ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('Native diagnostic: 856 shared blocks + two separate sets of 920 blocks\nPrefix allocations only; no tensor-copy, performance or original-stall causality claim',fontsize=11)
    root=Path('results/v3/figures');root.mkdir(exist_ok=True)
    for ext in ['png','svg']:fig.savefig(root/f'v5_pending_restore_blocks.{ext}',dpi=160)
    p=root/'v5_pending_restore_blocks.svg';p.write_text('\n'.join(l.rstrip() for l in p.read_text().splitlines())+'\n')


if __name__=='__main__':main()
