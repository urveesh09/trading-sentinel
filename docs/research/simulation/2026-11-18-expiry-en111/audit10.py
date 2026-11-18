"""Independent, offline round-9 review. Never rewrites the archived round."""
from pathlib import Path
import hashlib
import json
import sys
import unittest

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / '2026-11-18-expiry-en96'
sys.dont_write_bytecode = True
sys.path.insert(0, str(OLD))
import round8  # activates offline audit guard
import score9
import verify9
import test9_unit


def write(path, value):
    assert Path(path).resolve().parent == HERE.resolve()
    Path(path).write_text(json.dumps(value, indent=2, default=str) + '\n', encoding='utf-8')


def main():
    frozen, books = score9.verify_freeze()
    write(HERE / 'integrity10.json', dict(status='PASS', frozen_files=len(frozen['files']),
        data_files=len(frozen['data']['files']), dates={u: len(b) for u, b in books.items()},
        freeze_sha256=hashlib.sha256((OLD/'freeze9.json').read_bytes()).hexdigest()))
    print('Frozen source, data hashes and tape arrays PASS', flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromModule(test9_unit)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    write(HERE / 'mechanics10.json', dict(tests=result.testsRun, failures=len(result.failures),
        errors=len(result.errors), status='PASS' if result.wasSuccessful() else 'FAIL'))
    assert result.wasSuccessful()
    original_write = score9.write
    score9.write = lambda path, obj: write(HERE / ('fresh-' + Path(path).name), obj)
    try:
        verify9.main()
    finally:
        score9.write = original_write
    fresh = json.loads((HERE/'fresh-verification9.json').read_text())
    assert fresh['status'] == 'PASS', fresh
    print('Fresh independent verification PASS', flush=True)


if __name__ == '__main__':
    main()
