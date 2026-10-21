#!/usr/bin/env bash
set -euo pipefail
cd /workspace

bash scripts/set_mode.sh B3 dhas
engine_pid=$(supervisorctl pid cacheflow_vllm)
lmcache_pid=$(supervisorctl pid cacheflow_lmcache)
registry=results/raw/guard_holdout_pids.csv
printf 'run_id,policy,vllm_pid,lmcache_pid\n' > "$registry"

for spec in \
    'B3 dhas b3-revisit-8k-holdout-r3' \
    'B3 dhas_guarded b3g-revisit-8k-holdout-r1' \
    'B2 fifo b2-revisit-8k-holdout-r6' \
    'B2 fifo b2-revisit-8k-holdout-r7' \
    'B3 dhas_guarded b3g-revisit-8k-holdout-r2' \
    'B3 dhas b3-revisit-8k-holdout-r4'; do
    read -r mode policy run_id <<< "$spec"
    bash scripts/set_policy.sh "$mode" "$policy"
    [[ $(supervisorctl pid cacheflow_vllm) == "$engine_pid" ]]
    [[ $(supervisorctl pid cacheflow_lmcache) == "$lmcache_pid" ]]
    bash scripts/warm_reset.sh
    bash scripts/run_benchmark.sh "$run_id" long_doc_revisit 8192 8 4 64 11
    printf '%s,%s,%s,%s\n' "$run_id" "$policy" "$engine_pid" "$lmcache_pid" >> "$registry"
done
