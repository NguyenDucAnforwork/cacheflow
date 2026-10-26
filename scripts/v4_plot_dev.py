"""Run-level dev repetitions; show median tradeoff alongside tail improvement."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

main=json.loads(Path('results/v3/v4_vllm_dev_audit.json').read_text())['runs']
sg=json.loads(Path('results/v3/sglang/v4_validation_audit.json').read_text())['pairs']
fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
ax=axes[0]
arms=['fifo64','lpm_real16','bundle_wave16','packing_reuse64']
for offset,key,label,color in [(-.17,'p50_ms','p50','#4477aa'),(.17,'p95_ms','p95','#cc6677')]:
    values=[[r[key]/1000 for r in main if r['arm']==a] for a in arms]
    x=np.arange(len(arms))+offset
    ax.bar(x,[np.mean(v) for v in values],width=.32,label=label,color=color,alpha=.75)
    for xx,v in zip(x,values):ax.scatter([xx]*len(v),v,s=14,color='#222222',zorder=3)
ax.set_xticks(range(4),['FIFO64','GPU-LPM16','Bundle16','Union64'])
ax.set_ylabel('Arrival TTFT (seconds)');ax.set_title('vLLM + LMCache: pressure dev');ax.legend()
ax=axes[1]
selected=[r for r in sg if '-qps4-native-' in r['a'] and '-lpm-qps4-' in r['canonical_b']]
assert len(selected)==3
for offset,key,label,color in [(-.17,'p50_ms_delta_pct','p50','#4477aa'),(.17,'p95_ms_delta_pct','p95','#cc6677')]:
    ax.bar(np.arange(3)+offset,[r[key] for r in selected],width=.32,color=color,alpha=.75,label=label)
ax.set_xticks(range(3),['Seed101','Seed102','Seed103']);ax.axhline(0,color='black',lw=.7)
ax.set_ylabel('Union vs native LPM change (%)');ax.set_title('HiCache Direct + guard: median cost');ax.legend()
for ax in axes:ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
fig.suptitle('Development only: 60 unique QA, three arrival schedules per contrast',fontsize=12)
for suffix in ['png','svg']:fig.savefig(f'results/v3/figures/v4_dev_tradeoffs.{suffix}',dpi=160)

svg=Path('results/v3/figures/v4_dev_tradeoffs.svg')
svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
