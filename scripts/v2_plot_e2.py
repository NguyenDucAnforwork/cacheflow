"""Render standalone run-level E2 figures from audited prompt-free tables."""
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

base = Path('results/v2')
rows = list(csv.DictReader((base / 'e2_runs.csv').open()))
fig, axes = plt.subplots(1, 3, figsize=(12, 3.7), layout='constrained')
colors = {'B1': '#2463a5', 'B2': '#d87818'}
budgets = sorted({int(r['gpu_kv_gib']) for r in rows})
for i, gib in enumerate(budgets):
    for arm, shift in [('B1', -.12), ('B2', .12)]:
        selected = [r for r in rows if int(r['gpu_kv_gib']) == gib and r['mode'] == arm]
        ttft = [float(r['arrival_ttft_p95_ms'])/1000 for r in selected]
        work = [float(r['computed_prefill_tokens'])/1000 for r in selected]
        label = arm if i == 0 else None
        axes[0].scatter([i+shift]*len(ttft), ttft, color=colors[arm], label=label, s=28, zorder=3)
        axes[0].plot([i+shift-.07, i+shift+.07], [np.mean(ttft)]*2, color=colors[arm], lw=2)
        axes[1].scatter([i+shift]*len(work), work, color=colors[arm], s=28)
        axes[1].plot([i+shift-.07, i+shift+.07], [np.mean(work)]*2, color=colors[arm], lw=2)
    pairs = {}
    for r in rows:
        if int(r['gpu_kv_gib']) == gib:
            pairs.setdefault(r['seed'], {})[r['mode']] = float(r['arrival_ttft_p95_ms'])/1000
    for pair in pairs.values():
        axes[0].plot([i-.12, i+.12], [pair['B1'], pair['B2']], color='#aaa', lw=.8, zorder=1)
    cpu = [float(r['actual_external_tokens'])/1000 for r in rows
           if int(r['gpu_kv_gib']) == gib and r['mode'] == 'B2' and r['actual_external_tokens']]
    axes[2].scatter([i]*len(cpu), cpu, color=colors['B2'], s=30)
    axes[2].plot([i-.07, i+.07], [np.mean(cpu)]*2, color=colors['B2'], lw=2)
for ax in axes:
    ax.set_xticks(range(len(budgets)), [f'{g} GiB' for g in budgets])
    ax.set_xlabel('GPU KV budget')
    ax.grid(axis='y', alpha=.25)
    ax.set_ylim(bottom=0)
    ax.spines[['top', 'right']].set_visible(False)
axes[0].set_title('Arrival TTFT p95 per run')
axes[0].set_ylabel('Seconds')
axes[0].legend(frameon=False)
axes[1].set_title('New prefill computation')
axes[1].set_ylabel('Thousands of tokens / run')
axes[2].set_title('Actual external KV tokens (B2)')
axes[2].set_ylabel('Thousands of tokens / run')
fig.suptitle('LoCoMo full-context dev subset · 3 conversations · 30 QA/run · 0.2 QPS\n'
             'Dots are independent arrival-seed runs; bars are means. CPU tier: 16 GiB.', fontsize=11)
fig.savefig(base / 'e2_tiering.png', dpi=180)
fig.savefig(base / 'e2_tiering.svg')
print(base / 'e2_tiering.png')
