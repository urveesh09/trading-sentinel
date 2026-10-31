"""Date-scoped research-clock repair. Never imported by the application."""
from __future__ import annotations
import argparse,json,subprocess,sys
from contextlib import contextmanager
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
sys.path.insert(0,str(PARENT))
import lab_broad as B
from config import settings

SPECIAL=frozenset(('2024-03-02','2024-05-18'))
LOCAL=HERE/'_local'
B.Y.EVALS=LOCAL/'evals'


@contextmanager
def scoped_clock(now):
    if now.date().isoformat() not in SPECIAL:
        yield
        return
    before=(settings.FNO_ENTRY_END_MIN,settings.FNO_HARD_FLAT_MIN)
    try:
        settings.FNO_ENTRY_END_MIN=min(before[0],720)
        settings.FNO_HARD_FLAT_MIN=min(before[1],745)
        yield
    finally:
        settings.FNO_ENTRY_END_MIN,settings.FNO_HARD_FLAT_MIN=before


def wrap(fn):
    def call(self,*args):
        with scoped_clock(args[-1]):
            return fn(self,*args)
    return call


def install():
    if not getattr(B.Y.BookReplay,'_o31ic_installed',False):
        B.Y.BookReplay._entry=wrap(B.Y.BookReplay._entry)
        B.Y.BookReplay._manage=wrap(B.Y.BookReplay._manage)
        B.Y.BookReplay._o31ic_installed=True


install()


def books(phase):
    if phase=='screen':out=B.books('screen')
    else:
        previous=B.HERE
        try:
            B.HERE=HERE
            out=B.books('selected')
        finally:B.HERE=previous
    return {n:{**b,'name':'O31iC|'+b['name']} for n,b in out.items()}


def freeze():
    B.Y.write_new(HERE/'freeze.json',{'schema':'o31ic_calendar_v1','parent_freeze':B.P.sha(PARENT/'freeze.json'),
        'sources':{p.relative_to(B.ROOT).as_posix():B.P.sha(p) for p in HERE.glob('*.py')},
        'plan_sha256':B.P.sha(HERE/'PLAN.md'),'dates':sorted(SPECIAL),'entry_end':720,'hard_flat':745,
        'reuse':'2025/2026 original screen only; override inactive by exact ISO date; all reused files hash-sealed',
        'rule':'unchanged parent selection and acceptance','can_place_orders':False,'qualified':False})


def verify(phase):
    B.verify('screen')
    f=json.loads((HERE/'freeze.json').read_text())
    assert f['parent_freeze']==B.P.sha(PARENT/'freeze.json')
    assert all(B.P.sha(B.ROOT/p)==h for p,h in f['sources'].items())
    assert f['plan_sha256']==B.P.sha(HERE/'PLAN.md')
    for name in ['freeze.json']+(['selection.json'] if phase=='selected' else []):
        p=HERE/name;rel=p.relative_to(B.ROOT).as_posix()
        assert json.loads(subprocess.check_output(['git','show','HEAD:'+rel],cwd=B.ROOT))==json.loads(p.read_text()),'uncommitted '+name


def init():
    B.L._init()
    install()


def run(jobs,phase):
    B.O27F.deny_network();verify(phase);B.C.table('year')
    with ProcessPoolExecutor(max_workers=jobs,initializer=init) as pool:
        runner=B.Y.Runner(pool,jobs)
        runner.run(list(books(phase).values()),source='year',window=B.C.WINDOW)
    verify(phase)
    B.P.write(LOCAL/f'keys-{phase}-{B.YEAR}.json',{n:B.Y.task_key(b,'year',B.C.WINDOW) for n,b in books(phase).items()})
    print('DONE corrected',phase,B.YEAR,len(books(phase)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);p.add_argument('--jobs',type=int,default=3);p.add_argument('--phase',default='screen',choices=['screen','selected']);a=p.parse_args()
    if a.action=='freeze':freeze()
    else:run(a.jobs,a.phase)
