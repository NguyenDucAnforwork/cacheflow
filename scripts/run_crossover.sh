#!/usr/bin/env bash
set -euo pipefail
cd /workspace

bash scripts/set_mode.sh B2 fifo
engine_pid=$(supervisorctl pid cacheflow_vllm)
lmcache_pid=$(supervisorctl pid cacheflow_lmcache)
registry=results/raw/crossover_pids.csv
printf 'run_id,vllm_pid,lmcache_pid\n' > "$registry"

for spec in \
    'B2 fifo b2-simultaneous-live-r1' \
    'B3 dhas b3-simultaneous-live-r1' \
    'B3 dhas b3-simultaneous-live-r2' \
    'B2 fifo b2-simultaneous-live-r2'; do
    read -r mode policy run_id <<< "$spec"
    bash scripts/set_policy.sh "$mode" "$policy"
    [[ $(supervisorctl pid cacheflow_vllm) == "$engine_pid" ]]
    [[ $(supervisorctl pid cacheflow_lmcache) == "$lmcache_pid" ]]
    bash scripts/warm_reset.sh
    bash scripts/run_benchmark.sh "$run_id" long_doc_simultaneous 8192 8 4 64
    printf '%s,%s,%s\n' "$run_id" "$engine_pid" "$lmcache_pid" >> "$registry"
done
