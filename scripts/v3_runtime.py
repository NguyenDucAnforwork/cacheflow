"""Generate explicit V3 runtime settings; absent marker preserves V2 behavior."""
import argparse
import json
from pathlib import Path

import yaml
from v3_model import MODELS, get_model

ROOT = Path(__file__).resolve().parents[1]
MARKER = ROOT / '.cacheflow-v3-runtime.json'


def load():
    c = json.loads(MARKER.read_text())
    assert 1 <= c['max_inflight'] <= 64
    assert 1 <= c['max_num_seqs'] <= 32
    assert c['max_num_batched_tokens'] >= 2048
    assert c['chunk_size'] in [64, 128, 256, 512, 1024]
    assert isinstance(c['enforce_eager'], bool)
    c.setdefault('model_key', 'qwen3-1.7b')
    return c


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['configure', 'gateway', 'validate', 'vllm-args', 'model-path', 'model-name'])
    p.add_argument('--model', choices=list(MODELS), default='qwen3-1.7b')
    p.add_argument('--policy', choices=['fifo','static_group','dhas','dhas_guarded','lpm_hint','bundle_wave','lpm_real','packing_fifo','residency','packing','packing_reuse'],default='fifo')
    p.add_argument('--max-inflight', type=int, default=16)
    p.add_argument('--max-num-seqs', type=int, default=4)
    p.add_argument('--max-num-batched-tokens', type=int, default=8192)
    p.add_argument('--chunk-size', type=int, default=256)
    p.add_argument('--cuda-graphs', action='store_true')
    p.add_argument('--profile', action='store_true')
    p.add_argument('--kv-events', action='store_true')
    p.add_argument('--residency-events', action='store_true')
    p.add_argument('--kv-capacity-tokens', type=int, default=37424)
    p.add_argument('--keepalive-connections', type=int)
    p.add_argument('--max-bypasses', type=int)
    p.add_argument('--batch-invariant', action='store_true')
    args = p.parse_args()
    if args.command in ('configure', 'gateway'):
        c = dict(max_inflight=args.max_inflight, max_num_seqs=args.max_num_seqs,
                 max_num_batched_tokens=args.max_num_batched_tokens, chunk_size=args.chunk_size,
                 enforce_eager=not args.cuda_graphs, profile=args.profile, kv_events=args.kv_events,
                 residency_events=args.residency_events, kv_capacity_tokens=args.kv_capacity_tokens)
        c['model_key'] = args.model
        c['keepalive_connections'] = args.keepalive_connections if args.keepalive_connections is not None else 0
        c['max_bypasses'] = args.max_bypasses if args.max_bypasses is not None else 4
        c['batch_invariant'] = args.batch_invariant
        if args.command == 'gateway':
            c = load() | {'max_inflight': args.max_inflight}
            if args.keepalive_connections is not None:
                c['keepalive_connections']=args.keepalive_connections
            if args.max_bypasses is not None:
                c['max_bypasses']=args.max_bypasses
        MARKER.write_text(json.dumps(c, indent=2)+'\n')
        load()
        gateway = yaml.safe_load((ROOT/'configs/policies.yaml').read_text())
        gateway['scheduler']['max_inflight'] = c['max_inflight']
        gateway['scheduler']['policy'] = args.policy
        gateway['model'] = get_model(c['model_key'])['path']
        gateway['upstream_keepalive_connections']=c.get('keepalive_connections',0)
        gateway['residency'] = dict(enabled=c.get('residency_events', False),
                                   endpoint='ipc:///tmp/cacheflow-v3-kv-events.sock',
                                   kv_capacity_tokens=c.get('kv_capacity_tokens', 37424), max_bypasses=c.get('max_bypasses',4))
        (ROOT/'.cacheflow-policy').write_text(args.policy+'\n')
        (ROOT/'.cacheflow-v3-gateway.yaml').write_text(yaml.safe_dump(gateway))
    c = load()
    if args.command in ('model-path', 'model-name'):
        print(get_model(c['model_key'])['path' if args.command == 'model-path' else 'served_name'])
    elif args.command == 'vllm-args':
        out = ['--max-num-seqs', str(c['max_num_seqs']),
               '--max-num-batched-tokens', str(c['max_num_batched_tokens'])]
        if c['enforce_eager']:
            out.append('--enforce-eager')
        if c.get('residency_events'):
            out += ['--prefix-caching-hash-algo', 'sha256', '--kv-events-config',
                    json.dumps(dict(enable_kv_cache_events=True, publisher='zmq',
                        endpoint='ipc:///tmp/cacheflow-v3-kv-events.sock', replay_endpoint='tcp://127.0.0.1:5558'))]
        if c['profile']:
            out += ['--profiler-config', json.dumps(dict(profiler='torch',
                torch_profiler_dir=str(ROOT/'results/v3/raw/torch_profiles'),
                torch_profiler_with_stack=False, torch_profiler_record_shapes=True,
                ignore_frontend=True, max_iterations=120))]
        print('\n'.join(out))
    else:
        print(json.dumps(c, sort_keys=True))


if __name__ == '__main__':
    main()
