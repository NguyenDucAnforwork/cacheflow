"""CPU-only registration of a retained-run analysis correction, no serving."""
import inspect
import json
from datetime import datetime,timezone
from pathlib import Path
from v6_freeze_full import verify_full,sha
from v6_full_analysis_r1 import FIRST,REGISTRATION,audit_configuration


def main():
    assert not REGISTRATION.exists()
    from v4_services import service_pid
    for name in ['cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache','cacheflow_v3_sglang']:assert service_pid(name)==0,name
    parent,seal,freeze=verify_full();step=freeze['actions'][0];assert step['run_id']==FIRST
    from vllm.entrypoints.cli.serve import ServeSubcommand
    from vllm.utils.argparse_utils import FlexibleArgumentParser
    from v6_full_contracts import audit_configuration as old_configuration
    import vllm.entrypoints.cli.serve as serve
    import vllm.utils.argparse_utils as argparse_utils
    parser=FlexibleArgumentParser();ServeSubcommand().subparser_init(parser.add_subparsers())
    records=[];metadata={};raw={}
    for warm in [True,False]:
        rid=FIRST+('-warm' if warm else '');setup_path=Path(f'results/v3/{rid}.setup.json')
        setup=json.loads(setup_path.read_text());summary=json.loads(Path(f'results/v3/raw/{rid}.summary.json').read_text())
        entry=json.loads(Path(f'results/v3/{rid}.v6_entrypoint.json').read_text());argv=setup['actual_engine_argv_list']
        parsed=parser.parse_args(argv[argv.index('serve'):])
        assert parsed.max_num_seqs==16 and parsed.max_num_batched_tokens==8192 and parsed.kv_cache_memory_bytes==6*2**30
        args=(dict(step,run_id=rid),setup,summary,entry,parent,seal,freeze,warm)
        try:old_configuration(*args)
        except AssertionError:old_rejects=True
        else:old_rejects=False
        assert old_rejects
        audit_configuration(*args)
        records.append(dict(run_id=rid,all_max_num_seqs_values=[argv[i+1] for i,v in enumerate(argv) if v=='--max-num-seqs'],
            installed_parser_max_num_seqs=parsed.max_num_seqs,installed_parser_max_num_batched_tokens=parsed.max_num_batched_tokens,
            installed_parser_gpu_kv_bytes=parsed.kv_cache_memory_bytes,original_contract_rejects=True,corrected_contract_passes=True))
        for path in Path('results/v3').glob(rid+'.*.json'):metadata[str(path)]=sha(path)
        for suffix in ['.jsonl','.outputs.jsonl','.summary.json','.metrics.jsonl','.gateway.jsonl']:
            path=Path('results/v3/raw')/(rid+suffix);raw[str(path)]=sha(path)
    for name in ['results/v3/v6full1_interruption.json',f'results/v3/{FIRST}.invalid','results/v3/v6full1_execution.json']:
        metadata[name]=sha(name)
    sources=['scripts/v6_full_analysis_r1.py','scripts/v6_full_load_r1.py','scripts/v6_audit_full_run_r1.py','scripts/v6_register_analysis_r1.py']
    sources += [inspect.getfile(serve),inspect.getfile(argparse_utils)]
    r=dict(kind='analysis_only_duplicate_scalar_cli_correction',registered_utc=datetime.now(timezone.utc).isoformat(),
        retained_run_id=FIRST,reference_freeze_sha256=sha('results/v3/v6full1_freeze.json'),
        source_sha256={n:sha(n) for n in sources},retained_metadata_sha256=metadata,retained_raw_sha256=raw,parser_proof=records,
        scope='Original study stopped at audit. Original sources/seal/marker retained; installed vLLM parser resolves duplicate store option to16. R1 checks the final explicit scalar option, retains every other original contract/request check, and permits only the exact hashed audit-stage interruption marker. No inference retry or full-study completion claim. No parser dispatch/server/model construction performed.')
    with REGISTRATION.open('x') as out:out.write(json.dumps(r,indent=2)+'\n')
    print('Registered analysis correction',sha(REGISTRATION),flush=True)


if __name__=='__main__':main()
