"""Tests for base-revision dependency safeguards added after hidden-miss reports."""
from __future__ import annotations

import gzip
import json
import tempfile
import unittest
from pathlib import Path

from build_map import build_test_reference_map
from selector import Change, Engine, Hunk, is_safe_noop


class V3Improvements(unittest.TestCase):
    def test_test_reference_index_comes_from_base_test_bodies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / 'tests' / 'test_example.py'
            p.parent.mkdir()
            p.write_text('class TestFoo:\n    def test_one(self):\n        assert expr.SOME_OPTION\n'
                         '    def test_two(self):\n        assert something_else\n')
            refs = build_test_reference_map(root)
            self.assertIn('tests/test_example.py::TestFoo::test_one', refs['SOME_OPTION'])
            self.assertNotIn('tests/test_example.py::TestFoo::test_two', refs['SOME_OPTION'])

    def test_static_reference_expands_uncovered_function(self):
        tests = [
            {'number': 0, 'id': 'tests/test_example.py::TestFoo::test_one', 'file': 'tests/test_example.py', 'seconds': .1},
            {'number': 1, 'id': 'tests/test_else.py::TestFoo::test_other', 'file': 'tests/test_else.py', 'seconds': .1},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            engine = Engine(tests, base=base, ast_index={
                'sqlglot/formatter.py': {'functions': [[1, 5, 'uncommon_function']], 'classes': [], 'imports': []}
            }, coverage={'sqlglot/formatter.py': {}})
            engine.static_refs = {'uncommon_function': [tests[0]['id']]}
            ch = Change('sqlglot/formatter.py', 'sqlglot/formatter.py', [Hunk(3, 1, 3, 1, [('-', '    return False'), ('+', '    return True')])])
            self.assertIn(0, engine.affected(ch))

    def test_shared_test_helpers_trigger_fallback(self):
        tests = [
            {'number': 0, 'id': 'tests/test_a.py::test_a', 'file': 'tests/test_a.py', 'seconds': .1},
            {'number': 1, 'id': 'tests/test_b.py::test_b', 'file': 'tests/test_b.py', 'seconds': .1},
        ]
        engine = Engine(tests, ast_index={}, coverage={})
        ch = Change('tests/helpers.py', 'tests/helpers.py')
        self.assertEqual(engine.affected(ch), {0, 1})

    def test_fixture_optimizer_benchmarks_include_executor(self):
        tests = [
            {'number': 0, 'id': 'tests/test_optimizer.py::TestOptimizer::test_tpcds', 'file': 'tests/test_optimizer.py', 'seconds': .2},
            {'number': 1, 'id': 'tests/test_executor.py::TestExecutor::test_execute_tpcds', 'file': 'tests/test_executor.py', 'seconds': 21.454},
        ]
        engine = Engine(tests, ast_index={}, coverage={})
        ch = Change('tests/fixtures/optimizer/tpc-ds/example.sql', 'tests/fixtures/optimizer/tpc-ds/example.sql')
        self.assertIn(1, engine.affected(ch))

    def test_comment_directives_are_not_assumed_harmless(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            p = base / 'sqlglot' / 'test_code.py'
            p.parent.mkdir()
            p.write_text('def foo():\n    return 42\n')
            c = Change('sqlglot/test_code.py', 'sqlglot/test_code.py',
                       [Hunk(1, 1, 1, 2, [(' ', 'def foo():'), ('+', '    # pragma: no cover')])])
            self.assertFalse(is_safe_noop(c, base))

if __name__ == '__main__':
    unittest.main()
