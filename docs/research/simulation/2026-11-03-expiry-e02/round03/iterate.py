"""Round03: both 2024/2025 are seen. One lot before any other risk change."""
from dataclasses import asdict,replace
from pathlib import Path
import json,sys,math

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import data as D
import e02_lab as E
from audit import native_audit,fixed_entry_stress

ORIGINAL_CHOOSE=E.choose


def one_lot(t,i,d,rule,budget,cash,lot=None):
    lot=E.LOT if lot is None else lot
    picked=ORIGINAL_CHOOSE(t,i,d,rule,budget,cash,lot)
    if picked is None:return None
    j,lots,limit=picked
    ask=E.up(float(t.q[i,j,3])+E.half(float(t.q[i,j,3])))
    limit=E.down(min(ask*1.1,(min(budget,cash)-2*E.ORDER)/(lot*(1+E.BUY_RATE))))
    return (j,1,limit) if limit>=ask and E.reserve(limit,1,lot)<=min(budget,cash)+.01 else None


def run(tapes,rule,scenario='ordinary',details=False):
    saved=E.choose
    try:
        E.choose=one_lot
        return E.run_year(tapes,rule,scenario,details)
    finally:E.choose=saved


def diagnose():
    assert not (HERE/'sizing-diagnosis.json').exists()
    finals=json.loads((HERE.parent/'finalists.json').read_text());out={}
    for year in (2024,2025):
        tapes=D.load_year(year,exam=year==2024)
        out[str(year)]={}
        for name,params in finals.items():
            r=E.Rule(**params)
            out[str(year)][name]={}
            for sc in ('ordinary','adverse'):
                row=run(tapes,r,sc,True)
                count=sum(native_audit(t,r,d,sc) for t,d in zip(tapes,row['days']))
                out[str(year)][name][sc]=dict(one_lot=row,unbraked_multiple_lot=E.run_year(tapes,r,sc,False,brakes=False)['summary'],native_positions_checked=count)
                print('SIZING_DIAGNOSIS',year,name,sc,row['summary'],flush=True)
    D.dump(HERE/'sizing-diagnosis.json',out)


if __name__=='__main__':diagnose()
