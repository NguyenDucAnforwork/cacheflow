"""Audit declared V3 runtime against actual serving-process arguments."""
import argparse
import json
import re
from pathlib import Path


def verify(path):
    c=json.loads(path.read_text());argv=c['actual_engine_argv'];runtime=c['runtime']
    def value(flag):
        matches=re.findall(r'(?<!\S)'+re.escape(flag)+r'\s+(\S+)',argv)
        if not matches:raise ValueError('missing '+flag)
        return matches[-1]
    for field,flag in [('max_num_seqs','--max-num-seqs'),('max_num_batched_tokens','--max-num-batched-tokens')]:
        if int(value(flag))!=runtime[field]:raise ValueError('runtime/engine mismatch: '+field)
    if ('--enforce-eager' in argv)!=runtime['enforce_eager']:raise ValueError('eager mismatch')
    if int(value('--kv-cache-memory-bytes'))!=c['gpu_kv_bytes']:raise ValueError('KV budget mismatch')
    if c.get('model') and c['model']['path'] not in argv:raise ValueError('model path mismatch')
    if runtime.get('residency_events') and '"enable_kv_cache_events": true' not in argv:
        raise ValueError('KV publishing not enabled')
    return dict(run_id=c['run_id'],status='passed',engine_runtime_matches=True,
                graph_enabled=not runtime['enforce_eager'],model_key=runtime.get('model_key','qwen3-1.7b'))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('setups',nargs='+',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=[verify(p) for p in args.setups]
    args.output.write_text(json.dumps(dict(checks=result),indent=2)+'\n')
    print('Verified actual runtime for',len(result),'runs')
