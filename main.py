"""Runtime protocol entry point. stdout contains JSON lines ONLY."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from selector import Engine

DATA=Path('/data')

def main() -> int:
    try:
        content=json.loads((DATA/'tests.json').read_text(encoding='utf8'))
        tests=content['tests']
        engine=Engine(tests)
        for patch in sorted((DATA/'commits').glob('*.patch')):
            try:
                chosen=engine.select(patch.read_text(encoding='utf8',errors='replace'))
                workers=engine.allocate(chosen)
            except Exception as exc:
                # Fail safely: all tests rather than invalid/missing JSON.
                print(f'fallback for {patch.stem}: {exc}',file=sys.stderr)
                workers=engine.allocate(engine.all_ids)
            print(json.dumps({'commit':patch.stem,'workers':workers},separators=(',',':')),flush=True)
        return 0
    except Exception as exc:
        print(f'fatal: {exc}',file=sys.stderr)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
