"""Preserve shared work and isolate this research. Never stages owner doc tails."""
from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
LOCAL=HERE/'_local'
DOCS=('SYSTEM_GUIDE.md','NEXT_AGENT_PLAN.md','HANDOVER_CHECKLIST.md')

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        while b:=f.read(1024*1024):h.update(b)
    return h.hexdigest()

def git(*a,input=None,cwd=ROOT):return subprocess.check_output(['git',*a],cwd=cwd,input=input)

def save(name,x):
    p=HERE/name;assert not p.exists(),p
    p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def note(s):
    for n in DOCS:
        p=ROOT/'docs'/n;p.write_bytes(s.encode('utf-8')+b'\n\n'+p.read_bytes())

def bootstrap():
    LOCAL.mkdir(exist_ok=True);assert not (HERE/'initial.json').exists();originals={}
    for n in DOCS:
        p=ROOT/'docs'/n;(LOCAL/(n+'.initial')).write_bytes(p.read_bytes())
        (LOCAL/(n+'.head')).write_bytes(git('show','HEAD:docs/'+n));originals[n]=sha(p)
    paths=list((ROOT/'python-engine').glob('*.py'))+[ROOT/'docs/SYSTEM_CODE_ATLAS.md']
    for dirname in ('2026-11-03-expiry-e03','2026-11-03-expiry-e031','2026-11-03-expiry-e032',
                    '2026-11-03-expiry-e032-structure','2026-11-03-expiry-auction'):
        paths += [p for p in (HERE.parent/dirname).rglob('*') if p.is_file() and not any(s in p.parts for s in ('_local','__pycache__'))]
    prod=ROOT.parent/'Production_Trading-sentinel'
    save('initial.json',dict(head=git('rev-parse','HEAD').decode().strip(),initial_status=git('status','--short').decode(),
       owner=originals,files={p.relative_to(ROOT).as_posix():sha(p) for p in paths},
       data={str(y):sha(HERE.parent/f'2026-11-03-expiry-e02/_local/{y}.sqlite') for y in (2024,2025)},
       production_head=git('rev-parse','HEAD',cwd=prod).decode().strip(),production_diff=hashlib.sha256(git('diff','HEAD','--binary',cwd=prod)).hexdigest(),
       api_calls=0,year2023_read=False))
    note('## November 3 — expiry anticipation / modest-risk study (Dev research)\n\n'
      'Owner authorizes a little more research risk, not extreme risk or deployment. Fixed 25% extra '
      'reserve tests a second-lot runner against an equal-budget sizing control; a separate frozen '
      'study will test pre-move price/volume/OI/futures features. Plan: '
      '`docs/research/simulation/2026-11-03-expiry-anticipation/PLAN.md`. '
      '2024/2025 seen, 2023/future exam protected. Baseline first, preserve failures. '
      'No engine/flag/schema/Production/download or live capital change.')
    print('INPUTS_AND_OWNER_BYTES_FROZEN',len(paths))

def prefix(n):
    old=(LOCAL/(n+'.initial')).read_bytes();cur=(ROOT/'docs'/n).read_bytes();assert cur.endswith(old),n
    return cur[:-len(old)]

def stage():
    for n in DOCS:
        blob=git('hash-object','-w','--stdin',input=prefix(n)+(LOCAL/(n+'.head')).read_bytes()).decode().strip()
        git('update-index','--cacheinfo','100644',blob,'docs/'+n)
    print('OWN_PREFIXES_ONLY_STAGED')

def verify():
    f=json.loads((HERE/'initial.json').read_text())
    for n,want in f['owner'].items():assert sha(LOCAL/(n+'.initial'))==want;prefix(n)
    for n,want in f['files'].items():assert sha(ROOT/n)==want,n
    for y,want in f['data'].items():assert sha(HERE.parent/f'2026-11-03-expiry-e02/_local/{y}.sqlite')==want,y
    prod=ROOT.parent/'Production_Trading-sentinel'
    assert git('rev-parse','HEAD',cwd=prod).decode().strip()==f['production_head']
    assert hashlib.sha256(git('diff','HEAD','--binary',cwd=prod)).hexdigest()==f['production_diff']
    for n in DOCS:
        assert b'expiry-anticipation/PLAN.md' in git('show','HEAD:docs/'+n)
        assert not any(c<32 and c not in (9,10,13) for c in prefix(n))
    print('POST_COMMIT_VERIFIED',git('rev-parse','HEAD').decode().strip(),'owner/old work/data/Production preserved')

if __name__=='__main__':globals()[sys.argv[1]]()
