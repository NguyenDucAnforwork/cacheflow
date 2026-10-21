#!/usr/bin/env bash
set -euo pipefail
cd /workspace
/venv/main/bin/python scripts/smoke.py http://127.0.0.1:8000 >/tmp/cacheflow-last-warmup.txt
sleep 2  # let asynchronous stores finish before forced L1 clear
bash scripts/reset_caches.sh
