#!/usr/bin/env bash
set -euo pipefail
cp /workspace/configs/supervisor/cacheflow_*.conf /etc/supervisor/conf.d/
supervisorctl reread
supervisorctl update
supervisorctl status cacheflow_vllm cacheflow_lmcache cacheflow_gateway
