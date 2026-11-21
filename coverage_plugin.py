"""Profile function calls during each *base-revision* sqlglot pytest test.

Generates structural coverage data, never labels from failing patches.
"""
import json
import os
import sys
from pathlib import Path
import pytest

SOURCE = str(Path(os.environ.get('SQLGLOT_BASE','/opt/sqlglot')).resolve() / 'sqlglot') + os.sep
OUT = Path(os.environ.get('BLAST_COVERAGE_OUTPUT','/app/coverage-raw.jsonl'))

class CoveragePlugin:
    def __init__(self):
        self.active=set()
        self.cache={}
        self.handle=OUT.open('w',encoding='utf8')

    def profile(self,frame,event,arg):
        if event != 'call': return
        code=frame.f_code
        key=self.cache.get(code)
        if key is None and code not in self.cache:
            filename=code.co_filename
            if filename.startswith(SOURCE) and filename.endswith('.py'):
                path='sqlglot/'+os.path.relpath(filename,SOURCE).replace(os.sep,'/')
                key=f'{path}|{code.co_firstlineno}'
            self.cache[code]=key
        if key: self.active.add(key)

    @pytest.hookimpl(hookwrapper=True,tryfirst=True)
    def pytest_runtest_protocol(self,item,nextitem):
        self.active=set()
        sys.setprofile(self.profile)
        try:
            yield
        finally:
            sys.setprofile(None)
            self.handle.write(json.dumps([item.nodeid,sorted(self.active)],separators=(',',':'))+'\n')

    def pytest_sessionfinish(self,session,exitstatus):
        self.handle.close()

PLUGIN=CoveragePlugin()

def pytest_configure(config):
    config.pluginmanager.register(PLUGIN,name='blast_coverage_instrumentation')
