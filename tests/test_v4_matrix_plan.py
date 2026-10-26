import subprocess
from pathlib import Path


def test_actual_shell_matrix_routes_all_regimes_without_name_collisions_or_state_changes():
    markers=[Path('.cacheflow-v3-runtime.json'),Path('.cacheflow-sglang-runtime.json')]
    before={str(p):p.read_bytes() for p in markers if p.exists()}
    output=subprocess.check_output(['bash','scripts/v4_sglang_validate.sh','--plan'],text=True)
    rows=[line.split('\t') for line in output.splitlines()]
    assert [r[1:] for r in rows if r[0]=='ENGINE']==[['lpm','6'],['dfs-weight','6'],['lpm','10']]
    runs={r[1]:r[2] for r in rows if r[0]=='BENCH'}
    assert len(runs)==sum(r[0]=='BENCH' for r in rows)==37
    expected=set()
    for tag,arms in [('lpm-qps4',['native','fifo','union']),('dfs-weight-qps4',['native','union']),
                     ('lowreuse',['native','union']),('lpm-qps2',['native','union']),('gpufit',['native','union'])]:
        for seed in [101,102,103]:
            for arm in arms:expected.add(f'v4-validate2-{tag}-{arm}-s{seed}')
    actual={rid for rid in runs if '-warm-' not in rid}
    assert actual==expected and len(actual)==33
    for rid,trace in runs.items():
        assert Path(trace).is_file(),trace
        if 'lowreuse' in rid:assert 'lowreuse8' in trace
        elif 'qps2' in rid:assert 'qps2' in trace
        else:assert 'qps4' in trace
    assert {str(p):p.read_bytes() for p in markers if p.exists()}==before
    resumed=subprocess.check_output(['bash','scripts/v4_sglang_validate.sh','--plan','--resume-controls'],text=True)
    remaining=[r.split('\t')[1] for r in resumed.splitlines() if r.startswith('BENCH\t')]
    assert len(remaining)==len(set(remaining))==28
    assert not any('-lpm-qps4-' in rid for rid in remaining)
