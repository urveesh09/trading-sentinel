"""Versioned state-freshness input repair; parent sources remain frozen."""
import argparse,json,shutil,subprocess,sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timedelta
from pathlib import Path
HERE=Path(__file__).resolve().parent;PARENT=HERE.parent
sys.path.insert(0,str(PARENT))
import router_lab as X
ROOT=X.ROOT;LOCAL=HERE/'_local';X.Y.EVALS=LOCAL/'evals'
_original_state=X.state_at


def stale(bar,now):
    if bar is None:return True
    end=datetime.fromisoformat(bar).replace(tzinfo=now.tzinfo)+timedelta(minutes=5)
    return now-end>=timedelta(minutes=5)


def state_at(frame,now):
    row,bar,history=_original_state(frame,now)
    if stale(bar,now):return {'state':'UNAVAILABLE','raw_state':'UNAVAILABLE','stale_closed_bar':True},bar,{}
    return row,bar,history
X.state_at=state_at
X.model_file=lambda:LOCAL/f'models-{X.B.YEAR}.json'
X._MODELS=None


def books():return {n:{**b,'n01_state_freshness':'bar_end_age_lt5min'} for n,b in X.books('candidate').items()}


def freeze():
    assert not (HERE/'freeze.json').exists()
    X.write(HERE/'freeze.json',{'schema':'n01f_freshness_v1','parent_freeze_sha256':X.B.P.sha(PARENT/'freeze.json'),
        'sources':{p.relative_to(ROOT).as_posix():X.B.P.sha(p) for p in HERE.glob('*.py')},'plan_sha256':X.B.P.sha(HERE/'PLAN.md'),
        'rule':'Only state freshness repair; all parent strategy/training/acceptance parameters unchanged','qualified':False,'can_place_orders':False})


def verify(phase):
    X.verify('base');f=json.loads((HERE/'freeze.json').read_text())
    assert f['parent_freeze_sha256']==X.B.P.sha(PARENT/'freeze.json')
    assert all(X.B.P.sha(ROOT/p)==h for p,h in f['sources'].items())
    assert f['plan_sha256']==X.B.P.sha(HERE/'PLAN.md')
    for n in ['freeze.json']+(['training-manifest.json'] if phase=='candidate' else []):
        p=HERE/n;assert json.loads(subprocess.check_output(['git','show','HEAD:'+p.relative_to(ROOT).as_posix()],cwd=ROOT))==json.loads(p.read_text()),'uncommitted '+n
    if phase=='candidate':
        m=json.loads((HERE/'training-manifest.json').read_text())
        assert X.B.P.sha(X.model_file())==m['models'][X.B.YEAR]['sha256']
        assert all(X.B.P.sha(ROOT/p)==h for p,h in m['library_sha256'].items())


def run(jobs):
    X.B.O27F.deny_network();verify('candidate');X.C.table('year')
    with ProcessPoolExecutor(max_workers=jobs,initializer=X.init) as pool:
        worker=X.Y.Runner(pool,jobs);worker.run(list(books().values()),source='year',window=X.C.WINDOW)
    verify('candidate');X.write(LOCAL/f'keys-candidate-{X.B.YEAR}.json',{n:X.Y.task_key(b,'year',X.C.WINDOW) for n,b in books().items()})
    print('DONE fresh candidate',X.B.YEAR,len(books()),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);p.add_argument('--jobs',type=int,default=3);a=p.parse_args()
    if a.action=='freeze':freeze()
    else:run(a.jobs)
