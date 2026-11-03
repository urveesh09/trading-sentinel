"""Stage only this study's prepended doc slices; preserve owner changes.

Uses exact bytes and Git's index API; never stages the owner's original tails.
"""
from pathlib import Path
import subprocess,hashlib,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]

def run(*args,input=None):return subprocess.check_output(['git',*args],cwd=ROOT,input=input)

def own_prefix(name):
    original=(HERE/'_local'/(name+'.initial')).read_bytes()
    current=(ROOT/'docs'/name).read_bytes()
    assert current.endswith(original),'Owner working content changed; reconcile explicitly'
    return current[:-len(original)]

def stage_docs():
    for name in ('SYSTEM_GUIDE.md','NEXT_AGENT_PLAN.md','HANDOVER_CHECKLIST.md'):
        prefix=own_prefix(name)
        payload=prefix+(HERE/'_local'/(name+'.head')).read_bytes()
        blob=run('hash-object','-w','--stdin',input=payload).decode().strip()
        run('update-index','--cacheinfo','100644',blob,'docs/'+name)
    print('ONLY_E031_DOC_PREFIXES_STAGED; original owner bytes preserved')

def verify():
    frozen=json.loads((HERE/'initial-freeze.json').read_text())
    for name,want in frozen['owner_originals'].items():
        original=(HERE/'_local'/(name+'.initial')).read_bytes()
        assert hashlib.sha256(original).hexdigest()==want
        own_prefix(name)
    prod=ROOT.parent/'Production_Trading-sentinel'
    def pg(*args):return subprocess.check_output(['git',*args],cwd=prod)
    assert pg('rev-parse','HEAD').decode().strip()==frozen['production']['head']
    assert hashlib.sha256(pg('diff','HEAD','--binary')).hexdigest()==frozen['production']['diff_sha256']
    for path,want in frozen['inputs'].items():
        # Later native implementation may extend expiry_e02, never the research baseline.
        if path=='python-engine/expiry_e02.py':continue
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==want,path
    for v in frozen['datasets'].values():assert hashlib.sha256(Path(v['path']).read_bytes()).hexdigest()==v['sha256']
    forward=HERE/'forward-freeze.json'
    if forward.exists():
        for path,want in json.loads(forward.read_text())['source_sha256'].items():
            assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==want,path
        assert 'EXPIRY_E031_SHADOW_ENABLED:      bool  = False' in (ROOT/'python-engine/config.py').read_text(encoding='utf-8')
        assert (ROOT/'docs/EXPIRY_RESEARCH_E031.md').exists()
        assert (HERE/'README.md').exists()
    for name in frozen['owner_originals']:
        tracked=run('show','HEAD:docs/'+name).decode('utf-8')
        assert 'E03.1' in tracked and '2026-11-03-expiry-e031/PLAN.md' in tracked
        assert not any(c<32 and c not in (9,10,13) for c in own_prefix(name))
    print('POST_COMMIT_CONSISTENCY_PASSED; owner bytes/baseline/data/Production preserved; HEAD',run('rev-parse','HEAD').decode().strip())

if __name__=='__main__':
    import sys
    {'stage':stage_docs,'verify':verify}[sys.argv[1]]()
