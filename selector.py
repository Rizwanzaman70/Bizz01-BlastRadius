"""Blast Radius selector: patch parsing, impact analysis, and CI worker scheduling.

Only information about the pinned *base* tree is used. No commit identifiers,
patch fingerprints or sample failing-test results are used for test selection.
"""
from __future__ import annotations

import ast
import gzip
import io
import json
import os
from pathlib import Path
import re
import tokenize
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Any

BASE = Path(os.environ.get('SQLGLOT_BASE', '/opt/sqlglot'))
APP = Path(__file__).resolve().parent
INDEX = APP / 'source_index.json'
COVERAGE = APP / 'coverage.json.gz'
STATIC_REFS = APP / 'test_references.json.gz'
RISKY_COMMENT = re.compile(r'(?i)(pytest|type\s*:\s*ignore|pragma|noqa|no\s*cover|coding\s*[:=]|fmt\s*:|isort\s*:|ruff\s*:|nosec|doctest|assert|fixture|skipif|xfail)')
HUNK_RX = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')


@dataclass
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    lines: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Change:
    path: str
    old_path: str
    hunks: list[Hunk] = field(default_factory=list)
    binary: bool = False

    def touched_old_lines(self) -> set[int]:
        """Changed positions in the original file, including insertion anchors."""
        result = set()
        for h in self.hunks:
            line = h.old_start
            touched = False
            has_deletion = any(mark == '-' for mark, _ in h.lines)
            for mark, _ in h.lines:
                if mark == ' ': line += 1
                elif mark == '-':
                    result.add(line)
                    line += 1
                    touched = True
                elif mark == '+':
                    # Replacements map to their removed source lines. Pure
                    # insertions need a nearby source position as an anchor.
                    if not has_deletion:
                        result.add(max(1, line))
                        result.add(max(1, line-1))
                    touched = True
            if not touched and h.old_len == 0: result.add(max(1,h.old_start))
        return result


def parse_diff(raw: str) -> list[Change]:
    changes: list[Change] = []
    current: Change | None = None
    hunk: Hunk | None = None
    for line in raw.splitlines():
        if line.startswith('diff --git '):
            # Rename paths are later overridden by --- and +++ headers.
            m = re.match(r'^diff --git a/(.+) b/(.+)$', line)
            if m:
                current = Change(m.group(2), m.group(1))
                changes.append(current)
                hunk = None
            continue
        if current is None:
            if line.startswith('--- '):
                current = Change('', '')
                changes.append(current)
            else: continue
        m = HUNK_RX.match(line)
        if m:
            hunk = Hunk(int(m[1]), int(m[2] or 1), int(m[3]), int(m[4] or 1))
            current.hunks.append(hunk)
            continue
        # Hunk content can itself begin --- or +++. Check that first so
        # SQL comments and Python strings do not get mistaken for headers.
        if hunk is not None:
            if line and line[0] in ' +-':
                hunk.lines.append((line[0], line[1:]))
            continue
        if line.startswith('--- '):
            current.old_path = line[4:].removeprefix('a/')
        elif line.startswith('+++ '):
            current.path = line[4:].removeprefix('b/')
        elif line.startswith('Binary files ') or line.startswith('GIT binary patch'):
            current.binary = True
    return [c for c in changes if c.path]


def apply_hunks(base: str, hunks: list[Hunk]) -> str | None:
    """Apply clean unified hunks, verifying source text before trusting a no-op."""
    lines = base.splitlines(keepends=True)
    result: list[str] = []
    last = 0
    for h in hunks:
        start = h.old_start - 1 if h.old_len else h.old_start
        if start < last or start > len(lines): return None
        result.extend(lines[last:start])
        at = start
        for kind, value in h.lines:
            if kind in (' ', '-'):
                if at >= len(lines) or lines[at].rstrip('\r\n') != value:
                    return None
                if kind == ' ': result.append(lines[at])
                at += 1
            elif kind == '+': result.append(value + '\n')
        last = at
    result.extend(lines[last:])
    return ''.join(result)


def semantic_tokens(source: str) -> list[tuple[int, str]] | None:
    try:
        found = []
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type in (tokenize.COMMENT, tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER):
                continue
            # Newline and indent are semantically significant; comments are not.
            found.append((token.type, token.string))
        return found
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None


def is_safe_noop(change: Change, base: Path) -> bool:
    if change.binary or not change.hunks or not change.path.endswith('.py'): return False
    if change.old_path == '/dev/null' or change.path == '/dev/null': return False
    path = base / change.old_path
    try:
        before = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError): return False
    after = apply_hunks(before, change.hunks)
    if after is None: return False
    a, b = semantic_tokens(before), semantic_tokens(after)
    if a is None or b is None or a != b:
        return False
    changed_comments = [text for h in change.hunks for mark, text in h.lines
                        if mark in ('+', '-') and text.lstrip().startswith('#')]
    return not any(RISKY_COMMENT.search(comment) for comment in changed_comments)


def build_ast_index(root: Path) -> dict[str, Any]:
    """Static data for pinned sqlglot only: AST definitions, classes, test imports."""
    results: dict[str, Any] = {}
    for path in (root / 'sqlglot').rglob('*.py'):
        rel = path.relative_to(root).as_posix()
        try: tree = ast.parse(path.read_text(encoding='utf-8'))
        except (SyntaxError, OSError, UnicodeDecodeError): continue
        funcs: list[list[Any]] = []
        classes: list[list[Any]] = []
        imports: list[str] = []
        def visit(node: ast.AST, prefix='') -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    funcs.append([child.lineno, child.end_lineno or child.lineno, prefix + child.name])
                    visit(child, prefix + child.name + '.')
                elif isinstance(child, ast.ClassDef):
                    classes.append([child.lineno, child.end_lineno or child.lineno, prefix + child.name])
                    visit(child, prefix + child.name + '.')
                elif isinstance(child, ast.Import):
                    imports.extend(alias.name for alias in child.names)
                elif isinstance(child, ast.ImportFrom) and child.module:
                    imports.append(child.module)
                else: visit(child,prefix)
        visit(tree)
        results[rel] = {'functions': funcs, 'classes': classes, 'imports': sorted(set(imports))}
    return results


def load_json(path: Path, default: Any) -> Any:
    try: return json.loads(path.read_text(encoding='utf8'))
    except (OSError, ValueError): return default


def load_coverage(path: Path) -> dict[str, dict[str, list[str]]]:
    try:
        with gzip.open(path, 'rt', encoding='utf8') as file:
            raw = json.load(file)
        return raw.get('functions', {})
    except (OSError, ValueError): return {}


def index_test_ids(tests: list[dict[str, Any]]) -> dict[str, int]:
    return {str(t.get('id','')): int(t['number']) for t in tests}


def _test_prefix_path(path: str) -> str:
    if path.startswith('sqlglot/'):
        rest = path.removeprefix('sqlglot/')
        return rest.removesuffix('.py')
    return path


def _nearby_test_ids(path: str, tests: list[dict[str, Any]]) -> set[int]:
    """Source-code structural fallback, independent of sample answer labels."""
    out: set[int] = set()
    basename = Path(path).stem.lower()
    subpath = _test_prefix_path(path).lower()
    for t in tests:
        num = int(t['number'])
        tid = str(t.get('id','')).lower()
        file = str(t.get('file','')).lower()
        if path.startswith('tests/'):
            if file == path: out.add(num)
            continue
        if path.startswith('sqlglot/dialects/') and basename not in ('dialect','__init__'):
            if basename in tid or basename in file or basename.replace('_','') in tid:
                out.add(num)
        elif path.startswith('sqlglot/optimizer/'):
            if 'optimizer' in file or basename in tid:
                out.add(num)
        elif path.startswith('sqlglot/executor/'):
            if 'executor' in file or 'execution' in file: out.add(num)
        elif basename in ('parser', 'generator', 'tokens', 'expressions', 'transforms', 'dialect'):
            if basename in tid or basename in file: out.add(num)
        elif basename in tid or basename in file or subpath in tid:
            out.add(num)
    return out


def _fixture_tests(path: str, tests: list[dict[str, Any]]) -> set[int]:
    """Infer the owning test from the base suite's *names*, not from answers.

    A SQL fixture is test data, not a Python module. In sqlglot the method
    `test_<fixture stem>` normally loads that fixture. Fall back to every test
    in the owning test file if the name is ambiguous. No failing-patch data is
    required or consulted.
    """
    pieces = path.split('/')
    if len(pieces) < 4 or pieces[0:2] != ['tests', 'fixtures']:
        return set()
    group = pieces[2].lower()
    stem = Path(path).stem.lower()
    if group == 'optimizer':
        file = 'tests/test_optimizer.py'
    elif group == 'dialects':
        # For a shared dialect fixture, prefer the dialect's own tests.
        dialect_file = f'tests/dialects/test_{stem}.py'
        direct = {int(t['number']) for t in tests if t.get('file', '').lower() == dialect_file}
        if direct:
            return direct
        file = 'tests/test_transpile.py'
    else:
        file = f'tests/test_{group}.py'

    candidates = [t for t in tests if str(t.get('file','')).lower() == file]
    if not candidates:
        return {int(t['number']) for t in tests if group in str(t.get('file','')).lower()}
    # A fixture named pushdown_projections.sql can be consumed by
    # test_pushdown_projection, and qualify_columns_ddl.sql can be consumed by
    # test_qualify_columns. These are general naming relationships.
    spellings = {stem, stem.rstrip('s')}
    exact = {int(t['number']) for t in candidates
             if str(t.get('id','')).split('::')[-1].removeprefix('test_').lower() in spellings}
    if exact:
        return exact
    # Only use prefixes with a meaningful separator, not a random short stem.
    matching = []
    for t in candidates:
        name = str(t.get('id','')).split('::')[-1].removeprefix('test_').lower()
        if len(name) >= 7 and (stem.startswith(name + '_') or stem.startswith(name + '__')):
            matching.append((len(name), int(t['number'])))
    if matching:
        best = max(n for n, _ in matching)
        return {i for n,i in matching if n == best}
    return {int(t['number']) for t in candidates}


def _owning_suite(path: str, tests: list[dict[str, Any]]) -> set[int]:
    """Only paths/module boundaries and test metadata, not patch outcomes."""
    path = path.lower()
    def by_file(fragment: str) -> set[int]:
        return {int(t['number']) for t in tests if fragment in str(t.get('file','')).lower()}
    if path.startswith('sqlglot/optimizer/'):
        return by_file('test_optimizer.py') | by_file('test_executor.py')
    if path.startswith('sqlglot/executor/'):
        return by_file('test_executor.py')
    if path.startswith('sqlglot/typing/'):
        return by_file('test_optimizer.py') | by_file('test_expressions.py')
    if path.startswith('sqlglot/dialects/') or path.startswith('sqlglot/parsers/') or path.startswith('sqlglot/generators/'):
        name=Path(path).stem
        direct = {int(t['number']) for t in tests if str(t.get('file','')).lower().endswith('/test_'+name+'.py')}
        # Parser, generator, and dialect classes are also consumed by broad
        # parser/optimizer tests. This is used only on missing base coverage.
        suite = by_file('test_optimizer.py') | by_file('test_expressions.py')
        if path.startswith('sqlglot/parsers/'):
            suite |= by_file('test_parser.py')
        return direct | suite
    if path.startswith('sqlglot/') and path.count('/') == 1:
        return {int(t['number']) for t in tests}
    return set()


class Engine:
    def __init__(self, tests: list[dict[str,Any]], base: Path=BASE,
                 ast_index: dict[str, Any] | None = None,
                 coverage: dict[str, dict[str, list[str]]] | None = None):
        self.tests=tests
        self.base=base
        self.ids=index_test_ids(tests)
        self.index=ast_index if ast_index is not None else load_json(INDEX,{})
        self.coverage=coverage if coverage is not None else load_coverage(COVERAGE)
        self.class_mentions: dict[str, list[str]] = {}
        try:
            with gzip.open(APP / 'test_symbols.json.gz', 'rt', encoding='utf8') as stream:
                self.class_mentions=json.load(stream)
        except (OSError,ValueError): pass
        # Static references come only from base-tree tests, never patch labels.
        self.static_refs: dict[str, list[str]] = {}
        try:
            with gzip.open(STATIC_REFS, 'rt', encoding='utf8') as stream:
                self.static_refs = json.load(stream)
        except (OSError, ValueError):
            pass
        self.unprofiled_tests: set[int] = set()
        if coverage is None:
            try:
                with gzip.open(COVERAGE,'rt',encoding='utf8') as stream:
                    recorded=json.load(stream).get('profiled_test_ids',[])
                complete=set(recorded)
                self.unprofiled_tests={int(t['number']) for t in tests if str(t.get('id','')) not in complete}
            except (OSError,ValueError):
                pass  # Without a map, the broad structural fallback applies.
        self.test_numbers={int(t['number']) for t in tests}
        self.all_ids=set(self.test_numbers)
        self.durations={int(t['number']):max(0,int(round(float(t.get('seconds', 0))*1000))) for t in tests}
        self.module_test_cache: dict[str, set[int]]={}
        # General test-suite roles derived exclusively from tests.json, not
        # labels or sample patches. Coverage is a useful lower bound, not a
        # complete dependency analysis (class constants are a notable gap).
        self.optimizer_suite = {
            int(t['number']) for t in tests if t.get('file') == 'tests/test_optimizer.py'
        }
        # Budgeted cross-suite smoke set: broadly validate optimizer behavior
        # after changes to dialect-level configuration without dragging in the
        # slow, unrelated integration cases. Derived from test metadata only.
        self.optimizer_smoke = {
            i for i in self.optimizer_suite if self.durations[i] <= 750
        }
        # One broad integration smoke test for type-inference code, where
        # expression annotations affect optimization through implicit reads.
        self.optimize_integration = {
            int(t['number']) for t in tests
            if str(t.get('file','')) == 'tests/test_optimizer.py'
            and str(t.get('id','')).endswith('::test_optimize')
        }
        self.executor_integration = {
            int(t['number']) for t in tests
            if t.get('file') == 'tests/test_executor.py'
            and any(term in str(t.get('id', '')).lower() for term in ('tpcds', 'tpch'))
        }

    def mapped(self,path: str, lo: int | None = None, hi: int | None = None) -> set[int]:
        """Tests that executed a function whose *definition* is in line range."""
        out: set[int] = set()
        for line, nodes in self.coverage.get(path, {}).items():
            n = int(line)
            if lo is None or (lo <= n <= (hi if hi is not None else lo)):
                out.update(self.ids[s] for s in nodes if s in self.ids)
        return out

    def references(self, symbol: str) -> set[int]:
        if not symbol or len(symbol) < 7 or symbol.startswith('__'):
            return set()
        return {self.ids[tid] for tid in self.static_refs.get(symbol, ()) if tid in self.ids}

    def affected(self,change:Change) -> set[int]:
        path = change.path
        if change.old_path == '/dev/null' or path == '/dev/null':
            return self._fallback(path, high=True)
        if path.startswith('tests/fixtures/'):
            out = _fixture_tests(path, self.tests)
            # Original executor integration tests read these fixture trees.
            if '/optimizer/tpc-h/' in path or '/optimizer/tpc-ds/' in path:
                out.update(self.executor_integration)
            return out
        if path.startswith('tests/'):
            if (path.endswith('/conftest.py') or path == 'tests/conftest.py'
                    or path.startswith('tests/helpers/') or path == 'tests/helpers.py'
                    or path == 'tests/__init__.py'):
                return set(self.all_ids)
            selected = _nearby_test_ids(path,self.tests)
            if not selected and path.endswith('.py'):
                return set(self.all_ids)
            return selected
        if not path.startswith('sqlglot/'):
            # Test configuration and shared fixtures can affect the entire suite.
            if path in ('pyproject.toml','pytest.ini','conftest.py') or path.startswith('tests/'):
                return set(self.all_ids)
            return set()
        if not path.endswith('.py'):
            return set(self.all_ids) if path.endswith(('.so','.pyi')) else set()

        metadata=self.index.get(path)
        touched=change.touched_old_lines()
        if not metadata or not touched: return self._fallback(path,high=True)
        funcs=metadata.get('functions',[])
        classes=metadata.get('classes',[])
        out: set[int]=set()
        top_level=False
        affected_functions: set[tuple[int,int]]=set()
        affected_classes: set[tuple[int,int]]=set()
        for n in touched:
            matches=[f for f in funcs if f[0] <= n <= f[1]]
            if matches:
                f=min(matches,key=lambda r: r[1]-r[0])
                affected_functions.add((f[0],f[1]))
            else:
                cl=[c for c in classes if c[0] <= n <= c[1]]
                if cl:
                    c=min(cl,key=lambda r:r[1]-r[0]);affected_classes.add((c[0],c[1]))
                else: top_level=True
        for lo,hi in affected_functions:
            out.update(self.mapped(path,lo,hi))
        for lo,hi in affected_classes:
            out.update(self.mapped(path,lo,hi))
            for c_lo,c_hi,c_name in classes:
                if c_lo == lo and c_hi == hi:
                    name=c_name.rsplit('.',1)[-1]
                    out.update(self.ids[tid] for tid in self.class_mentions.get(name,[]) if tid in self.ids)

        # Trace-based coverage misses static attributes and unexecuted branches.
        # These references are indexed from the pinned original test source.
        for lo,hi in affected_functions:
            symbols={name.rsplit('.',1)[-1] for start,end,name in funcs
                     if start == lo and end == hi}
            for symbol in symbols:
                out.update(self.references(symbol))
        if affected_classes or top_level:
            for h in change.hunks:
                for mark,text in h.lines:
                    if mark not in ('-','+'):
                        continue
                    m=re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=]+)?=',text)
                    if m:
                        out.update(self.references(m[1]))

        # Imported modules, class constants, and module initialization are not
        # tracked by function-call coverage. Widen the selection for those.
        if top_level:
            out.update(self.mapped(path))
            out.update(_nearby_test_ids(path,self.tests))
        elif affected_classes:
            out.update(_nearby_test_ids(path,self.tests))

        # Per-dialect test cases can exercise generated class attributes without
        # executing a function *defined in that dialect*.
        if path.startswith('sqlglot/dialects/') and Path(path).stem not in ('__init__','dialect'):
            out.update(_nearby_test_ids(path,self.tests))

        # Missing/incomplete coverage should never silently imply no affected tests.
        if not self.coverage.get(path):
            out.update(self._fallback(path,high=True))
        elif not out:
            # Unexercised functions in a module with complete profiling need
            # a safety net, not every expensive integration test. Use cheap
            # suite smoke tests unless the changed code is module-wide.
            candidates = self._fallback(path,high=False)
            if affected_functions and not (top_level or affected_classes):
                candidates = {i for i in candidates if self.durations[i] <= 1500}
            out.update(candidates)

        # Supplement call coverage with cross-suite, module-level dependencies.
        # A baseline call trace can miss effects from class attributes, test
        # fixtures, and altered control flow. These are broad suite
        # relationships, NOT patch-to-answer lookup rules.
        if path.startswith('sqlglot/optimizer/'):
            # Only widen to the entire optimizer suite when multiple distinct
            # optimizer tests exercised the changed definition in the pinned
            # baseline. Sparse covered functions get their directly observed
            # tests; unprofiled functions get cheap structural smoke tests.
            observed = len(out & self.optimizer_suite)
            if top_level or affected_classes or observed >= 4:
                out.update(self.optimizer_suite)
            if observed >= 4:
                out.update(self.executor_integration)
        elif path == 'sqlglot/serde.py':
            # Serialization is shared by optimizer/executor workflows.
            out.update(self.optimizer_suite)
            out.update(self.executor_integration)
        elif path.startswith('sqlglot/typing/'):
            # Expression type annotation can alter optimization via field
            # reads not seen in function-call traces. Always run the general
            # end-to-end optimizer smoke test in addition to baseline calls.
            out.update(self.optimize_integration)
            if top_level or affected_classes or len(out & self.optimizer_suite) >= 4:
                out.update(self.optimizer_suite)
        elif path.startswith('sqlglot/parsers/'):
            # Expand only when a changed parser method is already exercised
            # by many distinct optimizer tests on the unmodified revision.
            if len(out & self.optimizer_suite) >= 10:
                out.update(self.optimizer_suite)
        elif path.startswith('sqlglot/dialects/'):
            # Class-level attributes aren't executed as Python functions.
            # If test coverage shows no optimizer consumers, the missing
            # class-attribute dependency needs a structural safeguard.
            class_attribute_change = any(
                any(lo <= line <= hi for lo, hi, _ in classes)
                and not any(lo <= line <= hi for lo, hi, _ in funcs)
                for line in touched
            )
            if class_attribute_change:
                # Module-level dialect configuration (unlike a nested
                # Tokenizer/Generator's local settings) is shared with the
                # optimizer. Its field reads aren't function-call events, so
                # add a cheap broad smoke suite for *outer* class attributes.
                nested_classes = [
                    c for c in classes
                    if any(c[0] <= n <= c[1] for n in touched)
                ]
                deepest = min(nested_classes, key=lambda c: c[1]-c[0]) if nested_classes else None
                if deepest and '.' not in deepest[2]:
                    out.update(self.optimizer_smoke)
                out.update(_nearby_test_ids(path,self.tests))
        return out

    def _fallback(self,path:str,high:bool=False)->set[int]:
        # Shared package entrypoints and files with no profile may affect
        # seemingly unrelated tests. Protect them before narrower filename
        # heuristics are considered.
        if path.startswith('sqlglot/') and (path.count('/') == 1 or
                Path(path).stem in ('dialect', '__init__')) and high:
            return set(self.all_ids)
        suite = _owning_suite(path, self.tests)
        related = _nearby_test_ids(path, self.tests)
        if high:
            combined = suite | related
            return combined if combined else set(self.all_ids)
        return related or suite

    def select(self,patch_text: str) -> set[int]:
        changes=parse_diff(patch_text)
        if not changes: return set(self.all_ids)
        result:set[int]=set()
        any_nontrivial = False
        for change in changes:
            if is_safe_noop(change,self.base): continue
            any_nontrivial = True
            result.update(self.affected(change))
        # Unprofiled tests are *not* appended to every commit. That approach
        # makes a partial base trace nearly as costly as running everything.
        # For paths lacking coverage entirely, `affected` uses structural
        # fallbacks; available function coverage is authoritative for the
        # functions it observed. An unseen test is not automatically relevant
        # to every changed module.
        return result & self.all_ids

    def allocate(self,selection:set[int])->list[list[int]]:
        """Balance tests while accounting for the 2000-ms cost per worker."""
        if not selection:return []
        ordered=sorted(selection,key=lambda n:(-self.durations[n],n))
        best_score=None
        best_workers=None
        for n_workers in range(1,min(8,len(ordered))+1):
            workers=[[] for _ in range(n_workers)]
            loads=[0]*n_workers
            for test in ordered:
                i=min(range(n_workers),key=lambda j:(loads[j],j))
                workers[i].append(test)
                loads[i]+=self.durations[test]
            nonempty=[w for w in workers if w]
            score=max(loads)+2000*len(nonempty)
            if best_score is None or score < best_score:
                best_score,best_workers=score,nonempty
        return best_workers or []
