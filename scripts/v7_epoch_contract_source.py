"""Explicit dev/identity-only transformation of the original full contract."""


def configuration_source(parent):
    changes=[
        ('"""Configuration proof for full-study arms; independent of collector assertions."""',
         '"""V7 development configuration proof, derived by explicit source transformation."""'),
        ('import yaml','import yaml\nimport copy\nfrom v6_full_analysis_r1 import scalar_argv'),
        ('def audit_configuration(', 'def base_configuration('),
        ("count=60 if warm else 1986;runtime=setup['runtime']",
         "count=60;runtime=setup['runtime']\n    if not sg:\n        setup=copy.deepcopy(setup)\n        setup['actual_engine_argv_list']=scalar_argv(setup['actual_engine_argv_list'],{'--max-num-seqs','--max-num-batched-tokens','--kv-cache-memory-bytes'})"),
        ("'gateway_source_sha256','v6_source_sha256'","'gateway_source_sha256','v6_source_sha256','v7_source_sha256'"),
        ("sc['hicache_size']==48","sc['hicache_size']==16"),
        ("runtime['host_kv_gib']==48","runtime['host_kv_gib']==16"),
        ("        if policy:assert 'cacheflow.v6_gateway:create_app' in setup['gateway_runtime_entrypoint']['argv']",
         "        required|={'scripts/v7_sglang_bench.py','scripts/v7_gateway_identity.py'}\n        if policy:assert 'cacheflow.v6_gateway:create_app' in setup['gateway_runtime_entrypoint']['argv']"),
        ("    expected=parent['source_sha256']|freeze['actor_sha256']",
         "    if policy:\n        required|={'src/cacheflow/v7_gateway.py','src/cacheflow/v7_epoch_scheduler.py','scripts/v7_gateway_identity.py','scripts/v7_serve_gateway.sh'}\n        assert {k:cfg['scheduler'][k] for k in ['block_size','min_shared_tokens','max_wait_ms','store_grace_ms','group_window_ms']}==dict(block_size=256,min_shared_tokens=1024,max_wait_ms=200,store_grace_ms=20,group_window_ms=30)\n    expected=parent['source_sha256']|freeze['actor_sha256']"),
    ]
    for old,new in changes:
        assert parent.count(old)==1,old
        parent=parent.replace(old,new,1)
    for old,new,count in [('3600','180',2),('cacheflow.v6_gateway:create_app','cacheflow.v7_gateway:create_app',2),("step['budget']","step['gpu_kv_gib']",6)]:
        assert parent.count(old)==count,(old,parent.count(old));parent=parent.replace(old,new)
    return parent
