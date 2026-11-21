"""Build AST index and optional pytest function-call coverage on pinned sqlglot.

Build-time only; failures or time budget exhaustion preserve partial trace data.
"""
import ast
import gzip
import json
import os
import subprocess
import sys
from pathlib import Path
from collections import defaultdict
from selector import build_ast_index, BASE, APP


def build_test_symbol_map(root: Path) -> dict[str,list[str]]:
    """Map classes mentioned by individual base test methods (not patches)."""
    uses=defaultdict(set)
    for path in (root / 'tests').rglob('test_*.py'):
        rel=path.relative_to(root).as_posix()
        try: tree=ast.parse(path.read_text(encoding='utf8'))
        except (OSError,SyntaxError,UnicodeDecodeError): continue
        def scan(node, suite):
            if isinstance(node, (ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith('test_'):
                ident=rel+'::'+'::'.join([*suite,node.name])
                for stmt in ast.walk(node):
                    symbol=None
                    if isinstance(stmt,ast.Attribute):symbol=stmt.attr
                    elif isinstance(stmt,ast.Name):symbol=stmt.id
                    if symbol and symbol[0].isupper() and symbol.isidentifier():
                        uses[symbol].add(ident)
                return
            if isinstance(node,ast.ClassDef):
                suite=[*suite,node.name]
            for child in getattr(node,'body',[]):
                if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                    scan(child,suite)
        scan(tree,[])
    return {symbol:sorted(ids) for symbol,ids in uses.items()}


def main():
    print('Preparing source AST index ...',flush=True)
    (APP/'source_index.json').write_text(json.dumps(build_ast_index(BASE),separators=(',',':')))
    with gzip.open(APP/'test_symbols.json.gz','wt',encoding='utf8') as stream:
        json.dump(build_test_symbol_map(BASE),stream,separators=(',',':'))
    raw=APP/'coverage-raw.jsonl'
    env=dict(os.environ)
    env['SQLGLOT_BASE']=str(BASE)
    env['SKIP_INTEGRATION']='0'
    env['BLAST_COVERAGE_OUTPUT']=str(raw)
    env['PYTHONPATH']=f'{APP}:{BASE}'+(os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    cmd=[sys.executable,'-m','pytest','-q','--tb=no','-p','coverage_plugin','tests']
    print('Tracing pinned-revision tests (bounded to 330 seconds)...',flush=True)
    try:
        with (APP/'coverage-build.log').open('wb') as log:
            proc=subprocess.run(cmd,cwd=BASE,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=330)
        print(f'Pytest tracing exit status: {proc.returncode}',flush=True)
    except subprocess.TimeoutExpired:
        print('Coverage budget reached, using partial profiling data',flush=True)
    except Exception as exc:
        print(f'Could not profile tests: {exc}',flush=True)
    out=defaultdict(lambda: defaultdict(set))
    count=0
    profiled_ids=set()
    if raw.exists():
        for row in raw.read_text(encoding='utf8').splitlines():
            try:
                tid,keys=json.loads(row)
                profiled_ids.add(tid)
                count+=1
                for key in keys:
                    path,line=key.rsplit('|',1)
                    out[path][line].add(tid)
            except (ValueError,KeyError,TypeError):continue
    data={'version':1,'tests_profiled':count,'profiled_test_ids':sorted(profiled_ids),'functions':{p:{line:sorted(ids) for line,ids in loc.items()} for p,loc in out.items()}}
    with gzip.open(APP/'coverage.json.gz','wt',encoding='utf8',compresslevel=6) as handle:
        json.dump(data,handle,separators=(',',':'))
    print(f'Coverage map: {count} base tests, {len(out)} source modules',flush=True)
    raw.unlink(missing_ok=True)
    (APP/'coverage-build.log').unlink(missing_ok=True)

if __name__=='__main__':main()
