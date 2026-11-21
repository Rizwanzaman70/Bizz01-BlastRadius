"""Fast local tests against made-up data; no competition answer labels."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from selector import (parse_diff, apply_hunks, is_safe_noop, semantic_tokens,
                      build_ast_index, Engine, _fixture_tests)


class BlastRadiusTests(unittest.TestCase):
    def test_multihunk_parser(self):
        diff='''diff --git a/sqlglot/parser.py b/sqlglot/parser.py
--- a/sqlglot/parser.py
+++ b/sqlglot/parser.py
@@ -3,2 +3,2 @@
-def x():
+def y():
     pass
@@ -9,1 +9,2 @@
 old
+new
'''
        changes=parse_diff(diff)
        self.assertEqual(len(changes),1)
        self.assertEqual(len(changes[0].hunks),2)
        self.assertIn(3,changes[0].touched_old_lines())
        self.assertIn(9,changes[0].touched_old_lines())

    def test_comment_noop(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            f=root/'sqlglot'/'parser.py'
            f.parent.mkdir();f.write_text('def f():\n    return 1 #old\n')
            patch='''diff --git a/sqlglot/parser.py b/sqlglot/parser.py
--- a/sqlglot/parser.py
+++ b/sqlglot/parser.py
@@ -1,2 +1,2 @@
 def f():
-    return 1 #old
+    return 1 #new
'''
            change=parse_diff(patch)[0]
            self.assertTrue(is_safe_noop(change,root))
            changed=apply_hunks(f.read_text(),change.hunks)
            self.assertIn('#new',changed)

    def test_string_change_is_not_comment(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);f=root/'sqlglot'/'dialects'/'x.py'
            f.parent.mkdir(parents=True)
            f.write_text('VALUE = "#old"\n')
            patch='''diff --git a/sqlglot/dialects/x.py b/sqlglot/dialects/x.py
--- a/sqlglot/dialects/x.py
+++ b/sqlglot/dialects/x.py
@@ -1 +1 @@
-VALUE = "#old"
+VALUE = "#new"
'''
            self.assertFalse(is_safe_noop(parse_diff(patch)[0],root))

    def test_coverage_selection_and_worker_balancing(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);f=root/'sqlglot'/'parser.py'
            f.parent.mkdir();f.write_text('def foo():\n    return 1\n\ndef bar():\n    return 2\n')
            index=build_ast_index(root)
            tests=[{'number':0,'id':'tests/test_parser.py::test_foo','file':'tests/test_parser.py','seconds':1.2},
                   {'number':1,'id':'tests/test_parser.py::test_bar','file':'tests/test_parser.py','seconds':1.0}]
            cov={'sqlglot/parser.py':{'1':['tests/test_parser.py::test_foo'],
                                      '4':['tests/test_parser.py::test_bar']}}
            engine=Engine(tests,base=root,ast_index=index,coverage=cov)
            patch='''diff --git a/sqlglot/parser.py b/sqlglot/parser.py
--- a/sqlglot/parser.py
+++ b/sqlglot/parser.py
@@ -2 +2 @@
-    return 1
+    return 3
'''
            self.assertEqual(engine.select(patch),{0})
            self.assertEqual(engine.allocate({0}),[[0]])
            self.assertEqual(engine.allocate(set()),[])

    def test_stdout_protocol(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);f=root/'sqlglot'/'dialects'/'x.py'
            f.parent.mkdir(parents=True);f.write_text('def x():\n    return 2\n')
            tests=[{'number':42,'id':'tests/test_dialects.py::TestX::test_thing','file':'tests/test_dialects.py','seconds':0.2}]
            engine=Engine(tests,root,build_ast_index(root),{})
            patch='''diff --git a/sqlglot/dialects/x.py b/sqlglot/dialects/x.py
--- a/sqlglot/dialects/x.py
+++ b/sqlglot/dialects/x.py
@@ -2 +2 @@
-    return 2
+    return 4
'''
            output={'commit':'abc123','workers':engine.allocate(engine.select(patch))}
            self.assertEqual(json.loads(json.dumps(output))['workers'],[[42]])

    def test_fixture_name_to_single_test(self):
        tests=[
          {'number':1,'id':'tests/test_optimizer.py::TestOptimizer::test_simplify','file':'tests/test_optimizer.py','seconds':0.2},
          {'number':2,'id':'tests/test_optimizer.py::TestOptimizer::test_merge_subqueries','file':'tests/test_optimizer.py','seconds':0.2},
          {'number':3,'id':'tests/test_optimizer.py::TestOptimizer::test_qualify_columns','file':'tests/test_optimizer.py','seconds':0.2},
          {'number':4,'id':'tests/test_optimizer.py::TestOptimizer::test_qualify_columns__invalid','file':'tests/test_optimizer.py','seconds':0.2},
        ]
        self.assertEqual(_fixture_tests('tests/fixtures/optimizer/simplify.sql', tests), {1})
        self.assertEqual(_fixture_tests('tests/fixtures/optimizer/qualify_columns__invalid.sql', tests), {4})
        self.assertEqual(_fixture_tests('tests/fixtures/optimizer/qualify_columns_ddl.sql', tests), {3})
        e=Engine(tests,ast_index={},coverage={})
        patch='''diff --git a/tests/fixtures/optimizer/simplify.sql b/tests/fixtures/optimizer/simplify.sql
--- a/tests/fixtures/optimizer/simplify.sql
+++ b/tests/fixtures/optimizer/simplify.sql
@@ -1 +1 @@
-a
+b
'''
        self.assertEqual(e.select(patch),{1})

    def test_outer_dialect_attributes_get_budgeted_optimizer_smoke(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root/'sqlglot'/'dialects'/'demo.py'
            f.parent.mkdir(parents=True)
            f.write_text('class Demo:\n    CONFIG = 1\n    class Tokenizer:\n        TOKEN = 4\n')
            tests = [
                {'number': 0, 'id': 'tests/test_optimizer.py::TestOptimizer::test_fast',
                 'file': 'tests/test_optimizer.py', 'seconds': 0.11},
                {'number': 1, 'id': 'tests/test_optimizer.py::TestOptimizer::test_expensive',
                 'file': 'tests/test_optimizer.py', 'seconds': 10.0},
                {'number': 2, 'id': 'tests/dialects/test_demo.py::TestDemo::test_demo',
                 'file': 'tests/dialects/test_demo.py', 'seconds': 0.03},
            ]
            engine = Engine(tests, base=root, ast_index=build_ast_index(root), coverage={
                'sqlglot/dialects/demo.py': {'2': ['tests/dialects/test_demo.py::TestDemo::test_demo']},
            })
            patch = """diff --git a/sqlglot/dialects/demo.py
--- a/sqlglot/dialects/demo.py
+++ b/sqlglot/dialects/demo.py
@@ -1,3 +1,3 @@
 class Demo:
-    CONFIG = 1
+    CONFIG = 2
     class Tokenizer:
"""
            self.assertEqual(engine.select(patch), {0, 2})

    def test_typing_helper_includes_general_integration_smoke(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root/'sqlglot'/'typing'/'demo.py'
            f.parent.mkdir(parents=True)
            f.write_text('def annotate(x):\n    return x + 1\n')
            tests = [
                {'number': 0, 'id': 'tests/test_optimizer.py::TestOptimizer::test_optimize',
                 'file': 'tests/test_optimizer.py', 'seconds': 0.3},
                {'number': 1, 'id': 'tests/test_optimizer.py::TestOptimizer::test_special',
                 'file': 'tests/test_optimizer.py', 'seconds': 9.0},
            ]
            engine = Engine(tests, base=root, ast_index=build_ast_index(root), coverage={
                'sqlglot/typing/demo.py': {'1': []},
            })
            patch = """diff --git a/sqlglot/typing/demo.py b/sqlglot/typing/demo.py
--- a/sqlglot/typing/demo.py
+++ b/sqlglot/typing/demo.py
@@ -1,2 +1,2 @@
 def annotate(x):
-    return x + 1
+    return x + 2
"""
            self.assertIn(0, engine.select(patch))

    def test_no_duplicate_workers_and_limits(self):
        tests=[{'number':i,'id':f'test::{i}','file':'test.py','seconds':i/10} for i in range(50)]
        engine=Engine(tests,ast_index={},coverage={})
        workers=engine.allocate(set(range(50)))
        self.assertLessEqual(len(workers),8)
        numbers=[n for group in workers for n in group]
        self.assertCountEqual(numbers,range(50))

if __name__=='__main__':unittest.main()
