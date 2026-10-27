"""Reviewable changes to the frozen native collector for future V7 identity.

Replay, metrics, reset, histogram, output capture and token accounting retain
the exact parent implementation. No source from the running study is edited.
"""


def native_source(parent):
    changes=[
        ('from v6_native_metrics import capture as capture_native,summarize as summarize_native',
         'from v6_native_metrics import capture as capture_native,summarize as summarize_native\nfrom v7_gateway_identity import capture as capture_gateway_identity,validate_replay_window as validate_gateway_pair'),
        ("p.add_argument('--replay-url');p.add_argument('--gateway-policy');p.add_argument('--warmup',action='store_true');args=p.parse_args()",
         "p.add_argument('--replay-url');p.add_argument('--gateway-policy');p.add_argument('--warmup',action='store_true');p.add_argument('--scheduler-implementation',choices=['reference','epoch']);args=p.parse_args()"),
        ("assert bool(args.gateway_policy)==bool(args.replay_url), 'gateway mode requires replay URL and policy together'",
         "assert bool(args.gateway_policy)==bool(args.replay_url), 'gateway mode requires replay URL and policy together'\n    assert bool(args.scheduler_implementation)==bool(args.gateway_policy),'Explicit implementation is required exactly for gateway arms'"),
        ("    if args.gateway_policy:\n        gateway_pid=int(subprocess.check_output",
         "    c['v7_source_sha256']={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in\n        ['scripts/v7_sglang_bench.py','scripts/v7_gateway_identity.py','src/cacheflow/v7_gateway.py','src/cacheflow/v7_epoch_scheduler.py','scripts/v7_serve_gateway.sh']}\n    if args.gateway_policy:\n        gateway_pid=int(subprocess.check_output"),
        ("assert 'cacheflow.v6_gateway:create_app' in gateway_argv","assert 'cacheflow.v7_gateway:create_app' in gateway_argv"),
        ("        c['gateway_runtime_entrypoint']=dict(pid=gateway_pid,argv=gateway_argv)",
         "        c['gateway_runtime_entrypoint']=dict(pid=gateway_pid,argv=gateway_argv)\n        c['gateway_implementation_before']=capture_gateway_identity(replay_url,args.gateway_policy,args.scheduler_implementation,require_fresh=True)"),
        ("        c['gateway_after']=after;setup.write_text(json.dumps(c,indent=2)+'\\n')",
         "        c['gateway_after']=after\n        c['gateway_implementation_after']=capture_gateway_identity(replay_url,args.gateway_policy,args.scheduler_implementation)\n        validate_gateway_pair(c['gateway_implementation_before'],c['gateway_implementation_after'],requests)\n        setup.write_text(json.dumps(c,indent=2)+'\\n')"),
    ]
    for old,new in changes:
        assert parent.count(old)==1,'Native parent collector no longer has the expected unique block'
        parent=parent.replace(old,new,1)
    return parent
