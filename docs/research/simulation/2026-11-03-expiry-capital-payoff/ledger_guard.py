"""Protect owner bytes, prior studies, selected-year inputs and Production."""
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
    LOCAL.mkdir(exist_ok=True);assert not (HERE/'initial.json').exists();owner={}
    for n in DOCS:
        p=ROOT/'docs'/n;(LOCAL/(n+'.initial')).write_bytes(p.read_bytes());(LOCAL/(n+'.head')).write_bytes(git('show','HEAD:docs/'+n));owner[n]=sha(p)
    paths=list((ROOT/'python-engine').glob('*.py'))+[ROOT/'docs/SYSTEM_CODE_ATLAS.md']
    for folder in ('2026-11-03-expiry-e03','2026-11-03-expiry-e031','2026-11-03-expiry-e032','2026-11-03-expiry-e032-structure',
                   '2026-11-03-expiry-anticipation','2026-11-03-expiry-auction'):
        paths += [p for p in (HERE.parent/folder).rglob('*') if p.is_file() and not any(x in p.parts for x in ('_local','__pycache__'))]
    prod=ROOT.parent/'Production_Trading-sentinel'
    save('initial.json',dict(head=git('rev-parse','HEAD').decode().strip(),owner=owner,initial_status=git('status','--short').decode(),
       files={p.relative_to(ROOT).as_posix():sha(p) for p in paths},
       data={str(y):sha(HERE.parent/f'2026-11-03-expiry-e02/_local/{y}.sqlite') for y in (2024,2025)},
       production_head=git('rev-parse','HEAD',cwd=prod).decode().strip(),production_diff=hashlib.sha256(git('diff','HEAD','--binary',cwd=prod)).hexdigest(),
       year2023_read=False,api_download_calls=0))
    note('## November 3 — capital reuse / directional payoff study (Dev research)\n\n'
       'Owner broadens research risk authority; no live risk or deployment follows. Test returned-cash '
       'turnover versus a funded daily loss ledger, and profit-only repeated original E03.1 entries. '
       'Separate protected directional-credit payoff round follows. Plan: '
       '`docs/research/simulation/2026-11-03-expiry-capital-payoff/PLAN.md`. '
       'Baseline first; 2024/2025 remain seen, 2023/future exam protected. '
       'No native/config/schema/Production/provider/download change. Earlier work/owner bytes preserved.')
    print('INITIAL_PRESERVED',len(paths),'files')

def prefix(n):
    original=(LOCAL/(n+'.initial')).read_bytes();current=(ROOT/'docs'/n).read_bytes();assert current.endswith(original),n
    return current[:-len(original)]

def stage():
    for n in DOCS:
        blob=git('hash-object','-w','--stdin',input=prefix(n)+(LOCAL/(n+'.head')).read_bytes()).decode().strip()
        git('update-index','--cacheinfo','100644',blob,'docs/'+n)
    print('ONLY_OWN_DOC_PREFIXES_STAGED')

def verify():
    initial=json.loads((HERE/'initial.json').read_text())
    for n,want in initial['owner'].items():assert sha(LOCAL/(n+'.initial'))==want;prefix(n)
    for n,want in initial['files'].items():assert sha(ROOT/n)==want,n
    for y,want in initial['data'].items():assert sha(HERE.parent/f'2026-11-03-expiry-e02/_local/{y}.sqlite')==want,y
    prod=ROOT.parent/'Production_Trading-sentinel'
    assert git('rev-parse','HEAD',cwd=prod).decode().strip()==initial['production_head']
    assert hashlib.sha256(git('diff','HEAD','--binary',cwd=prod)).hexdigest()==initial['production_diff']
    for n in DOCS:
        assert b'expiry-capital-payoff/PLAN.md' in git('show','HEAD:docs/'+n)
        assert not any(c<32 and c not in (9,10,13) for c in prefix(n))
    print('POST_COMMIT_VERIFIED',git('rev-parse','HEAD').decode().strip(),'owner/older evidence/data/Production preserved')

if __name__=='__main__':globals()[sys.argv[1]]()
