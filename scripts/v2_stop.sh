#!/usr/bin/env bash
set -euo pipefail
supervisorctl stop cacheflow_v2_gateway cacheflow_v2_vllm cacheflow_v2_lmcache >/dev/null 2>&1 || true
