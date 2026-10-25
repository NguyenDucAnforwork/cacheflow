#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for service in vllm lmcache gateway; do
    name="cacheflow_v2_$service"
    script="$root/scripts/v2_serve_$service.sh"
    cat > "/etc/supervisor/conf.d/$name.conf" <<EOF
[program:$name]
environment=PROC_NAME="%(program_name)s",CACHEFLOW_ROOT="$root"
command=$script
autostart=false
autorestart=unexpected
exitcodes=0
startsecs=5
stopasgroup=true
killasgroup=true
stopsignal=TERM
stopwaitsecs=30
stdout_logfile=/dev/stdout
redirect_stderr=true
stdout_logfile_maxbytes=0
EOF
done
supervisorctl reread
supervisorctl update
