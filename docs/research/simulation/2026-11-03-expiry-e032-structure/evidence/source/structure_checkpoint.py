"""Preserve owner work; selectively stage our doc prefixes; audit offline boundaries."""
from pathlib import Path
import hashlib, json, subprocess, sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LOCAL = HERE / '_local'
DOCS = ('SYSTEM_GUIDE.md', 'NEXT_AGENT_PLAN.md', 'HANDOVER_CHECKLIST.md')

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        while b := f.read(1024 * 1024): h.update(b)
    return h.hexdigest()

def git(*args, input=None, cwd=ROOT):
    return subprocess.check_output(['git', *args], cwd=cwd, input=input)

def note(text):
    for name in DOCS:
        p = ROOT / 'docs' / name
        p.write_bytes(text.encode('utf-8') + b'\n\n' + p.read_bytes())

def bootstrap():
    LOCAL.mkdir(exist_ok=True)
    assert not (HERE / 'initial.json').exists()
    originals = {}
    for name in DOCS:
        p = ROOT / 'docs' / name
        (LOCAL / (name + '.initial')).write_bytes(p.read_bytes())
        (LOCAL / (name + '.head')).write_bytes(git('show', 'HEAD:docs/' + name))
        originals[name] = sha(p)
    paths = list((ROOT/'python-engine').glob('*.py'))
    for d in ('2026-11-03-expiry-e031','2026-11-03-expiry-e032','2026-11-03-expiry-e03'):
        paths += [p for p in (HERE.parent/d).rglob('*') if p.is_file() and '_local' not in p.parts and '__pycache__' not in p.parts]
    data = HERE.parent/'2026-11-03-expiry-e02/_local'
    prod = ROOT.parent/'Production_Trading-sentinel'
    frozen = dict(head=git('rev-parse','HEAD').decode().strip(), owner=originals,
        files={p.relative_to(ROOT).as_posix():sha(p) for p in paths},
        data={str(y):sha(data/f'{y}.sqlite') for y in (2024,2025)},
        production_head=git('rev-parse','HEAD',cwd=prod).decode().strip(),
        production_diff=hashlib.sha256(git('diff','HEAD','--binary',cwd=prod)).hexdigest(),
        initial_status=git('status','--short').decode(),year2023_read=False,api_calls=0)
    (HERE/'initial.json').write_text(json.dumps(frozen,indent=2)+'\n',encoding='utf-8')
    note('## November 3 — E03.2 information/execution investigation (Dev only)\n\n'
         'Owner reopens research beyond the failed first E03.2 search. Plan: '
         '`docs/research/simulation/2026-11-03-expiry-e032-structure/PLAN.md`. '
         'Distinct option-price leadership and patient-entry mechanisms, frozen before scoring; '
         '2024/2025 remain seen, 2023 and the future exam protected. No engine, flag, '
         'Production, download or capital change. Baseline/parity first; accept failures.')
    print('BOOTSTRAP_PRESERVED',len(paths),'files')

def prefix(name):
    old=(LOCAL/(name+'.initial')).read_bytes();current=(ROOT/'docs'/name).read_bytes()
    assert current.endswith(old),name
    return current[:-len(old)]

def stage():
    for name in DOCS:
        payload=prefix(name)+(LOCAL/(name+'.head')).read_bytes()
        blob=git('hash-object','-w','--stdin',input=payload).decode().strip()
        git('update-index','--cacheinfo','100644',blob,'docs/'+name)
    print('OWN_PREFIXES_ONLY_STAGED')

def verify():
    f=json.loads((HERE/'initial.json').read_text(encoding='utf-8'))
    for name,want in f['owner'].items():
        assert sha(LOCAL/(name+'.initial'))==want;prefix(name)
    for path,want in f['files'].items(): assert sha(ROOT/path)==want,path
    for y,want in f['data'].items(): assert sha(HERE.parent/f'2026-11-03-expiry-e02/_local/{y}.sqlite')==want,y
    prod=ROOT.parent/'Production_Trading-sentinel'
    assert git('rev-parse','HEAD',cwd=prod).decode().strip()==f['production_head']
    assert hashlib.sha256(git('diff','HEAD','--binary',cwd=prod)).hexdigest()==f['production_diff']
    for name in DOCS:
        assert b'e032-structure/PLAN.md' in git('show','HEAD:docs/'+name)
        assert not any(c<32 and c not in (9,10,13) for c in prefix(name))
    print('POST_COMMIT_VERIFIED',git('rev-parse','HEAD').decode().strip(),'owner/source/data/Production preserved')

if __name__=='__main__': globals()[sys.argv[1]]()
