"""Prepare a metadata-only full-study namespace from a verified reference seal.

Never starts serving, deletes old results, or changes shared actors. Generated
controllers retain every policy/model/budget/timeout/trace choice. An AST proof
permits only namespace/path string changes and a fixed import-path bootstrap.
Opt-in analysis R1 additionally permits exactly the pinned scalar helper/call;
serving actors and the30-action graph remain unchanged.
"""
import argparse
import ast
import copy
import hashlib
import json
import re
from pathlib import Path

TEMPLATES=['v6_full.py','v6_full_plan.py','v6_freeze_full.py','v6_full_contracts.py','v6_audit_full_run.py','v6_audit_full.py',
    'v6_full_input_preflight.py','v6_token_fingerprints.py']
BOOTSTRAP="import sys as _namespace_sys\nfrom pathlib import Path as _NamespacePath\n_namespace_sys.path.insert(1, str(_NamespacePath(__file__).resolve().parents[2]))\n"


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def mapping(namespace):
    assert re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,47}',namespace) and 'v6full1' not in namespace
    bundle=Path('scripts/reproductions')/namespace
    replacements={str(Path('scripts')/n):str(bundle/n) for n in TEMPLATES}
    replacements['docs/V6_FULL_PROTOCOL.md']=f'docs/reproductions/{namespace}.md'
    return replacements


def rewrite(text,namespace):
    for before,after in mapping(namespace).items():text=text.replace(before,after)
    return text.replace('v6full1',namespace)


class RewriteStrings(ast.NodeTransformer):
    def __init__(self,namespace):self.namespace=namespace
    def visit_Constant(self,node):
        if isinstance(node.value,str):node.value=rewrite(node.value,self.namespace)
        return node


def verify_transform(original,generated,namespace):
    bootstrap=ast.parse(BOOTSTRAP).body;actual=ast.parse(generated)
    assert ast.dump(ast.Module(body=actual.body[:3],type_ignores=[]))==ast.dump(ast.Module(body=bootstrap,type_ignores=[]))
    expected=RewriteStrings(namespace).visit(copy.deepcopy(ast.parse(original)))
    actual.body=actual.body[3:]
    assert ast.dump(expected,include_attributes=False)==ast.dump(actual,include_attributes=False),'Nonmetadata AST change rejected'


def transformed(original,namespace):
    assert not any(isinstance(n,ast.Name) and n.id in {'_namespace_sys','_NamespacePath'} for n in ast.walk(ast.parse(original)))
    generated=BOOTSTRAP+rewrite(original,namespace);verify_transform(original,generated,namespace);compile(generated,'namespace_source','exec');return generated


def plan_from_source(source):
    tree=ast.parse(source);function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_plan')
    scope={};exec(compile(ast.Module(body=[function],type_ignores=[]),'namespace_plan_proof','exec'),scope)
    return scope['build_plan']()


SCALAR_FLAGS="{'--max-num-seqs','--max-num-batched-tokens','--kv-cache-memory-bytes'}"
SCALAR_ASSIGNMENT="argv=setup['actual_engine_argv_list'];lmargv=setup['actual_lmcache_argv_list']"


def scalar_definition(root):
    path=Path(root)/'scripts/v6_full_analysis_r1.py'
    tree=ast.parse(path.read_text())
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='scalar_argv']
    assert len(functions)==1
    return ast.unparse(functions[0])+'\n\n'


def verify_r1_transform(original,generated,namespace,normalizer):
    """Undo only the pinned scalar helper/call, then apply the original AST proof."""
    actual=ast.parse(generated);bootstrap=ast.parse(BOOTSTRAP).body
    assert ast.dump(ast.Module(body=actual.body[:3],type_ignores=[]))==ast.dump(ast.Module(body=bootstrap,type_ignores=[]))
    assert ast.dump(actual.body[3])==ast.dump(ast.parse(normalizer).body[0]),'Scalar helper changed'
    actual.body=actual.body[4:]
    class Undo(ast.NodeTransformer):
        found=0
        def visit_Call(self,node):
            if isinstance(node.func,ast.Name) and node.func.id=='scalar_argv':
                assert len(node.args)==2 and not node.keywords
                assert ast.dump(node.args[1])==ast.dump(ast.parse(SCALAR_FLAGS,mode='eval').body),'Audited flag set changed'
                self.found+=1
                return node.args[0]
            return self.generic_visit(node)
    undo=Undo();actual=undo.visit(actual);assert undo.found==1
    expected=RewriteStrings(namespace).visit(copy.deepcopy(ast.parse(original)))
    assert ast.dump(actual,include_attributes=False)==ast.dump(expected,include_attributes=False),'Change beyond scalar analysis correction'


def r1_contract(original,namespace,normalizer):
    generated=transformed(original,namespace)
    assert generated.count(SCALAR_ASSIGNMENT)==1
    generated=generated.replace(SCALAR_ASSIGNMENT,"argv=scalar_argv(setup['actual_engine_argv_list'], "+SCALAR_FLAGS+");lmargv=setup['actual_lmcache_argv_list']",1)
    generated=BOOTSTRAP+normalizer+generated[len(BOOTSTRAP):]
    verify_r1_transform(original,generated,namespace,normalizer);compile(generated,'namespace_r1_contract','exec')
    return generated


def r1_proof(root,reference):
    root=Path(root);path=root/'results/v3/v6full1_analysis_r1_registration.json';proof=json.loads(path.read_text())
    assert proof['kind']=='analysis_only_duplicate_scalar_cli_correction' and proof['reference_freeze_sha256']==sha(reference)
    helper='scripts/v6_full_analysis_r1.py';assert sha(root/helper)==proof['source_sha256'][helper]
    assert len(proof['parser_proof'])==2
    for row in proof['parser_proof']:
        assert row['installed_parser_max_num_seqs']==16 and row['installed_parser_max_num_batched_tokens']==8192
        assert row['installed_parser_gpu_kv_bytes']==6*2**30 and row['original_contract_rejects'] is True and row['corrected_contract_passes'] is True
    return dict(reference_registration_path='results/v3/v6full1_analysis_r1_registration.json',reference_registration_sha256=sha(path),
        scalar_source_path=helper,scalar_source_sha256=sha(root/helper),
        change='Copy exactly the pinned scalar_argv function and normalize the three audited main-engine scalar flags before the unchanged contract. Fresh namespace has no retained invalid-marker exception or reused measured arm.')


def prepare(namespace,reference,root=None,*,analysis_r1=False):
    root=Path.cwd() if root is None else Path(root);mapping(namespace)
    reference=Path(reference);reference=reference if reference.is_absolute() else root/reference
    freeze=json.loads(reference.read_text());assert freeze['status']=='frozen_prospective_full_study_not_completion'
    assert len(freeze['actions'])==30
    for key in ['actor_sha256','analysis_source_sha256','input_manifest_sha256','input_file_sha256','model_artifact_sha256','tokenizer_source_sha256','preflight_artifact_sha256','prerequisite_audit_sha256']:
        for name,digest in freeze.get(key,{}).items():assert sha(root/name)==digest,('Reference evidence changed',key,name)
    assert sha(root/'docs/V6_FULL_PROTOCOL.md')==freeze['plan_sha256']
    bundle_rel=Path('scripts/reproductions')/namespace;bundle=root/bundle_rel;doc_rel=Path(f'docs/reproductions/{namespace}.md');doc=root/doc_rel
    assert not bundle.exists() and not doc.exists(),'Namespace output already exists; preserve it'
    for base in [root/'results/v3',root/'results/v3/sglang']:
        assert not list(base.glob(namespace+'*')),'Namespace already has recorded results'
    contents={name:transformed((root/'scripts'/name).read_text(),namespace) for name in TEMPLATES}
    revision=r1_proof(root,reference) if analysis_r1 else None
    if analysis_r1:
        contents['v6_full_contracts.py']=r1_contract((root/'scripts/v6_full_contracts.py').read_text(),namespace,scalar_definition(root))
    before=plan_from_source((root/'scripts/v6_full_plan.py').read_text());after=plan_from_source(contents['v6_full_plan.py'])
    assert before==freeze['actions'] and len(after)==30
    assert after==[dict(s,run_id=s['run_id'].replace('v6full1',namespace)) for s in before],'Execution graph changed beyond run IDs'
    # All validation precedes file creation. No existing evidence is touched.
    bundle.mkdir(parents=True);doc.parent.mkdir(parents=True,exist_ok=True)
    files=[]
    for name,source in contents.items():
        path=bundle/name;path.write_text(source);files.append(dict(parent_path='scripts/'+name,parent_sha256=sha(root/'scripts'/name),path=str(bundle_rel/name),sha256=sha(path)))
    original_doc=(root/'docs/V6_FULL_PROTOCOL.md').read_text()
    difference=('Only run IDs/artifact paths/import lookup changed' if not analysis_r1 else 'Run IDs/artifact paths/import lookup changed; the separately recorded R1 scalar CLI interpretation correction is embedded in the analysis contract, with an AST proof permitting exactly that helper/call. No retained invalid marker is exempted and all30arms are fresh')
    doc.write_text(rewrite(original_doc,namespace)+f'\n\nNamespace reproduction of reference seal `{sha(reference)}`. {difference}; model, policies, traces, budgets, arrival schedules, transport and acceptance gates remain identical. This preparation does not start GPU work or reproduce numerical outcomes. Results remain a separate experiment.\n'+(f'\nR1 analysis lineage: `{revision["reference_registration_sha256"]}`; scalar helper source `{revision["scalar_source_sha256"]}`. The generated contract is hashed by this namespace’s own future full seal.\n' if revision else ''))
    manifest=dict(generator_sha256=sha(__file__),bootstrap_sha256=hashlib.sha256(BOOTSTRAP.encode()).hexdigest(),namespace=namespace,reference_freeze_path=str(reference),reference_freeze_sha256=sha(reference),files=files,
        protocol_path=str(doc_rel),protocol_sha256=sha(doc),actions=after,analysis_revision=revision,ast_proof=('Only constant string metadata rewrites plus fixed import-path bootstrap; full action graph identical except run IDs.' if not analysis_r1 else 'Same metadata proof for7modules; contract permits exactly the pinned scalar helper and one normalization call, then must reduce to the original AST. All30actions identical except IDs.'),
        commands=dict(plan=f'PYTHONPATH=src /venv/main/bin/python {bundle_rel}/v6_full.py --plan',
            freeze=f'PYTHONPATH=src /venv/main/bin/python {bundle_rel}/v6_freeze_full.py',
            execute=f'PYTHONPATH=src /venv/main/bin/python {bundle_rel}/v6_full.py'),
        scope='Prepared independent namespace, no serving calls or old-result removal. Reference shared actors must match; new seal/idle-services/development gates still required. No bit-exact output/performance promise across repetitions.')
    (bundle/'namespace_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return manifest


def main():
    p=argparse.ArgumentParser();p.add_argument('namespace');p.add_argument('--reference-freeze',type=Path,default=Path('results/v3/v6full1_freeze.json'));p.add_argument('--plan',action='store_true');p.add_argument('--analysis-r1',action='store_true');a=p.parse_args()
    mapping(a.namespace)
    if a.plan:print(json.dumps(dict(namespace=a.namespace,reference_freeze=str(a.reference_freeze),templates=TEMPLATES,analysis_r1=a.analysis_r1,operation='prepare source/protocol copies only; no serving or deletion'),indent=2));return
    result=prepare(a.namespace,a.reference_freeze,analysis_r1=a.analysis_r1)
    print(json.dumps(dict(namespace=a.namespace,commands=result['commands'],scope=result['scope']),indent=2))


if __name__=='__main__':main()
