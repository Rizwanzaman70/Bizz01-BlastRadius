"""Offline smoke test against the OFFICIAL starter scorer; not a Docker score.

No labels are consumed by the selector. The organizer's answers.json is read
only by score.py to report misses AFTER predictions have been generated.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from selector import Engine


def main() -> int:
    if len(sys.argv) != 2:
        print('usage: python benchmark_offline.py <extracted-official-starter-folder>', file=sys.stderr)
        return 2
    kit = Path(sys.argv[1]).resolve()
    data = kit / 'sample'
    if not all(p.exists() for p in (data / 'tests.json', data / 'answers.json', kit / 'score.py')):
        print('Expected official kit root with sample/tests.json, sample/answers.json and score.py',file=sys.stderr)
        return 2
    tests = json.loads((data / 'tests.json').read_text())['tests']
    engine = Engine(tests, base=Path('/nonexistent-sqlglot'), ast_index={}, coverage={})
    with tempfile.TemporaryDirectory(prefix='bizz01-offline-') as tmp:
        output = Path(tmp) / 'predictions.jsonl'
        with output.open('w', encoding='utf8') as stream:
            for path in sorted((data / 'commits').glob('*.patch')):
                selected = engine.select(path.read_text(encoding='utf8',errors='replace'))
                workers = engine.allocate(selected)
                stream.write(json.dumps({'commit':path.stem,'workers':workers},separators=(',',':')) + '\n')
        print('NOTE: No base checkout or coverage; this is a fallback-only smoke test.',flush=True)
        return subprocess.call([sys.executable,str(kit/'score.py'),str(data),str(data/'answers.json'),str(output)])


if __name__ == '__main__':
    raise SystemExit(main())
