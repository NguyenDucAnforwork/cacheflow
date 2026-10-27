"""Fresh-process opt-in one-site lookup watermark correction.

No native import, installation or upstream-file write on module import. The
original method AST is retained except its lookup watermark expression. Proofs
are written at actual connector construction, outside request measurement.
"""
import ast
import copy
import functools
import hashlib
import inspect
import json
import os
from pathlib import Path
import time
from types import CodeType


def code_record(code):
    # marshal is not canonical: reference/interning flags can change its bytes
    # even for the same code object. Serialize explicit semantic code fields.
    def constant(value):
        if isinstance(value,CodeType):return dict(code=code_record(value))
        if isinstance(value,bytes):return dict(bytes=value.hex())
        if isinstance(value,tuple):return dict(tuple=[constant(v) for v in value])
        if value is Ellipsis:return dict(ellipsis=True)
        if isinstance(value,(str,int,float,bool)) or value is None:return value
        raise TypeError('Unsupported code constant: '+type(value).__name__)
    return dict(bytecode=code.co_code.hex(),constants=[constant(v) for v in code.co_consts],
        names=code.co_names,varnames=code.co_varnames,freevars=code.co_freevars,cellvars=code.co_cellvars,
        argcount=code.co_argcount,posonly=code.co_posonlyargcount,kwonly=code.co_kwonlyargcount,flags=code.co_flags,
        exceptiontable=code.co_exceptiontable.hex(),filename=code.co_filename,firstlineno=code.co_firstlineno,qualname=code.co_qualname)


def code_sha(fn):return hashlib.sha256(json.dumps(code_record(inspect.unwrap(fn).__code__),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def method_node(source):
    tree=ast.parse(source);classes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LMCacheMPConnector'];assert len(classes)==1
    methods=[n for n in classes[0].body if isinstance(n,ast.FunctionDef) and n.name=='get_num_new_matched_tokens'];assert len(methods)==1
    node=copy.deepcopy(methods[0]);assert not node.decorator_list,'Unexpected native decorator'
    return node


def corrected_node(source):
    node=method_node(source);original=ast.dump(node,include_attributes=False)
    class Replace(ast.NodeTransformer):
        count=0
        def visit_Expr(self,n):
            if isinstance(n.value,ast.Call) and ast.unparse(n.value)=='tracker.increase_num_stored_tokens(ret)':
                self.count+=1
                return ast.copy_location(ast.parse('tracker.num_stored_tokens=max(tracker.num_stored_tokens,ret)').body[0],n)
            return self.generic_visit(n)
    transform=Replace();node=transform.visit(node);assert transform.count==1,'Native lookup update changed; stop before activation'
    ast.fix_missing_locations(node)
    proof=dict(replacements=1,original_method_ast_sha256=hashlib.sha256(original.encode()).hexdigest(),
        effective_method_ast_sha256=hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest(),
        change='Only cached lookup watermark update: additive ret becomes max(current,ret). Real incremental STORE updates and all lookup return/control paths unchanged.')
    return node,proof


def install(module,mode,proof_prefix,expected_source_sha256):
    if mode not in {'reference','idempotent'}:raise ValueError('Explicit reference/idempotent native mode required')
    if not proof_prefix:raise ValueError('Fresh constructor-proof prefix required')
    cls=module.LMCacheMPConnector
    if getattr(cls,'_cacheflow_v9_watermark_mode',None) is not None:
        if cls._cacheflow_v9_watermark_mode!=mode:raise RuntimeError('Cannot change native watermark mode in one process')
        return
    source_path=Path(module.__file__).resolve();source=source_path.read_text();digest=hashlib.sha256(source.encode()).hexdigest()
    assert digest==expected_source_sha256,'Unexpected installed connector source'
    original=cls.get_num_new_matched_tokens
    assert not original.__code__.co_freevars and Path(original.__code__.co_filename).resolve()==source_path,'Require original native method in a fresh import'
    native=method_node(source);_,transform=corrected_node(source)
    if mode=='idempotent':
        effective,_=corrected_node(source)
        compiled=ast.fix_missing_locations(ast.Module(body=[effective],type_ignores=[]))
        # Native globals are copied, not modified. Calls retain references to
        # the original logger/types; no unrelated native function is replaced.
        scope=dict(vars(module));exec(compile(compiled,str(source_path)+'::cacheflow_v9_idempotent','exec'),scope)
        fn=scope['get_num_new_matched_tokens'];fn.__module__=original.__module__;fn.__qualname__=original.__qualname__;fn.__annotations__=dict(original.__annotations__)
        cls.get_num_new_matched_tokens=fn
    effective=cls.get_num_new_matched_tokens
    expected_code=code_sha(effective);original_init=cls.__init__
    record=dict(mode=mode,code_fingerprint_version=1,native_source_path=str(source_path),native_source_sha256=digest,
        installer_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        original_method_code_sha256=code_sha(original),effective_method_code_sha256=expected_code,
        original_method_ast_sha256=hashlib.sha256(ast.dump(native,include_attributes=False).encode()).hexdigest(),
        effective_method_ast_sha256=transform['effective_method_ast_sha256'] if mode=='idempotent' else transform['original_method_ast_sha256'],
        functional_replacements=1 if mode=='idempotent' else 0,
        scope='Actual fresh connector construction identity. No per-call observer, STORE/DMA/performance/quality or liveness claim.')
    @functools.wraps(original_init)
    def initialize(self,*args,**kwargs):
        result=original_init(self,*args,**kwargs)
        bound=self.get_num_new_matched_tokens
        assert bound.__func__ is effective and code_sha(bound)==expected_code,'Actual connector dispatch differs from registered method'
        path=Path(f'{proof_prefix}.{os.getpid()}.jsonl');path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a') as out:
            out.write(json.dumps(dict(record,pid=os.getpid(),monotonic_ns=time.monotonic_ns(),
                connector_class=type(self).__module__+'.'+type(self).__qualname__,connector_role=str(getattr(self,'role',None))),sort_keys=True)+'\n')
        return result
    cls.__init__=initialize;cls._cacheflow_v9_watermark_mode=mode
