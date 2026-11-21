"""Archive extraction tests using synthetic archives, no network required."""
from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from fetch_sqlglot import PREFIX, extract_pinned_archive


def fake_archive() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(mode='w:gz', fileobj=buf) as tar:
        files = {
            f'{PREFIX}/sqlglot/__init__.py': b'VALUE = 1\n',
            f'{PREFIX}/sqlglot/parser.py': b'def parse(): pass\n',
            f'{PREFIX}/tests/test_demo.py': b'print(1)\n',
        }
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo(f'{PREFIX}/tests/parser_link.py')
        link.type = tarfile.SYMTYPE
        link.linkname = '../sqlglot/parser.py'
        tar.addfile(link)
        evil = tarfile.TarInfo(f'{PREFIX}/tests/outside_link')
        evil.type = tarfile.SYMTYPE
        evil.linkname = '../../../outside.py'
        tar.addfile(evil)
    return buf.getvalue()


class TarTests(unittest.TestCase):
    def test_symlinks_inside_repo_are_preserved_and_escaping_links_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / 'sqlglot'
            extract_pinned_archive(fake_archive(), dest)
            self.assertEqual((dest / 'sqlglot/__init__.py').read_text(), 'VALUE = 1\n')
            self.assertEqual((dest / 'tests/parser_link.py').read_text(), 'def parse(): pass\n')
            self.assertTrue((dest / 'tests/parser_link.py').is_symlink())
            self.assertFalse((dest / 'tests/outside_link').exists())


if __name__ == '__main__':
    unittest.main()
