"""Regression tests for baseline-source dependency safeguards."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from build_map import build_test_reference_map
from selector import Change, Engine, Hunk, is_safe_noop

class V3Tests(unittest.TestCase):
    def test_static_reference_index(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            file=root/'tests'/'test_example.py'
            file.parent.mkdir()
            file.write_text("class TestFoo:\n    def test_one(self):\n        assert exp.SOME_OPTION\n")
            data=build_test_reference_map(root)
            self.assertIn('tests/test_example.py::TestFoo::test_one', data['SOME_OPTION'])

    def test_shared_helper_change(self):
        tests=[{'number':0,'id':'tests/test_a.py::test_a','file':'tests/test_a.py','seconds':.1},
               {'number':1,'id':'tests/test_b.py::test_b','file':'tests/test_b.py','seconds':.1}]
        e=Engine(tests,ast_index={},coverage={})
        self.assertEqual(e.affected(Change('tests/helpers.py','tests/helpers.py')),{0,1})

    def test_critical_comment(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            file=root/'sqlglot'/'example.py'
            file.parent.mkdir()
            file.write_text('def f():\n    return 1\n')
            ch=Change('sqlglot/example.py','sqlglot/example.py',[
                Hunk(1,1,1,2,[(' ','def f():'),('+','    # pragma: no cover')])
            ])
            self.assertFalse(is_safe_noop(ch,root))

if __name__=='__main__':
    unittest.main()
