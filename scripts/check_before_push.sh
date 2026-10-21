#!/usr/bin/env bash
set -euo pipefail
git -C /workspace diff --cached --check
if git -C /workspace grep --cached -I -n -E '(ghp_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|hf_[A-Za-z0-9]{20,}|BEGIN OPENSSH PRIVATE KEY)' -- . ':!scripts/check_before_push.sh'; then
    echo 'Potential credential in staged content; refusing commit/push.' >&2
    exit 2
fi
