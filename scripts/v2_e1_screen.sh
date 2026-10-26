#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
prefix=${1:?usage: v2_e1_screen.sh PREFIX_TOKENS PAIRS FOLLOWER_OFFSET_MS [REPLICATE]}
pairs=${2:?missing pairs}
offset=${3:?missing follower offset}
rep=${4:-1}
case "$prefix" in 2048|4096|8192) ;; *) echo "prefix must be 2048, 4096 or 8192" >&2; exit 2 ;; esac
case "$pairs" in 1|4|8) ;; *) echo "pairs must be 1, 4 or 8" >&2; exit 2 ;; esac
case "$offset" in 0|50|200|500|1000) ;; *) echo "offset must be 0, 50, 200, 500 or 1000 ms" >&2; exit 2 ;; esac
[[ "$rep" =~ ^[1-9][0-9]*$ ]] || { echo "replicate must be positive integer" >&2; exit 2; }
cd "$root"
label="$((prefix / 1024))k-${offset}ms-${pairs}pairs"
trace="data/processed/v2/e1_$label.jsonl"
b2="v2-e1-b2-$label-r$rep"
b3="v2-e1-b3-$label-r$rep"
for run_id in "$b2" "$b3"; do
    if [[ -e "results/v2/raw/$run_id.jsonl" || -e "results/v2/raw/$run_id.summary.json" ]]; then
        echo "duplicate run ID: $run_id" >&2
        exit 1
    fi
done
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
/venv/main/bin/python scripts/v2_prefix_probe.py \
    --tokenizer-path /workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e \
    --output "$trace" --prefix-tokens "$prefix" --pairs "$pairs" \
    --follower-offset-ms "$offset" --seed 7
cleanup() { bash scripts/v2_stop.sh || true; }
trap cleanup EXIT
bash scripts/v2_start.sh B2 fifo 8
bash scripts/v2_reset.sh
bash scripts/v2_run.sh "$b2" "$trace"
bash scripts/v2_set_policy.sh dhas
bash scripts/v2_reset.sh
bash scripts/v2_run.sh "$b3" "$trace"
python3 scripts/v2_compare_e1.py --b2 "$b2" --b3 "$b3" \
    --output "results/v2/e1-$label-r$rep.compare.json"
