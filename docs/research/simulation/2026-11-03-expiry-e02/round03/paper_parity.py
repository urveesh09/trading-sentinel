"""Pure native signal/action parity and disclosed forward-basis sensitivities."""
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
import ast,json,subprocess,sys
import iterate as I
import data as D
import e02_lab as E
import expiry_e02 as X


def trade_peak(tapes,rule,scenario):
    cash=peak=E.START_CASH;days=[];saved=E.choose
    try:
        E.choose=I.one_lot
        for t in tapes:
            dd=peak-cash;scale=0 if dd>=4000 else .25 if dd>=3000 else .5 if dd>=1500 else 1.
            row=E.run_day(t,rule,scenario,cash,min(2500*scale,cash),True)
            for p in row['positions']:
                cash=round(cash+p['net'],2);peak=max(peak,cash)
            row['cash_after']=cash;days.append(row)
    finally:E.choose=saved
    return E.summary(days)


def main():
    candidate=json.loads((I.HERE/'candidate.json').read_text())
    rule=E.Rule(**candidate['rule']);checked=0
    tapes={y:D.load_year(y,exam=y==2024) for y in (2024,2025)}
    for year,days in tapes.items():
        for t in days:
            dirs=E.directions(t,rule);bars=[]
            for i in range(t.n):
                bars.append(dict(end=t.now[i].isoformat(),s=[float(v) for v in t.x[i]],f=[float(v) for v in t.f[i]]))
                answer=X.signal(bars)
                assert (answer.direction if answer else 0)==int(dirs[i]),(t.day,i,answer,dirs[i])
                checked+=1
    # Added held-quote plumbing must not change existing expiry money/policies.
    name='python-engine/expiry_paper.py'
    old=subprocess.check_output(['git','show','f2b95cd:'+name],cwd=D.ROOT).decode('utf-8-sig')
    current=(D.ROOT/name).read_text(encoding='utf-8-sig')
    def semantic(source):
        t=ast.parse(source);t.body=[n for n in t.body if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) or n.name!='_tick_underlying']
        return ast.dump(t,include_attributes=False)
    assert semantic(old)==semantic(current),'Existing expiry policy/money changed'
    sensitivity={}
    for year,days in tapes.items():
        sensitivity[str(year)]={s:dict(trade_close_peak=trade_peak(days,rule,s),warmup_1311=I.run(days,replace(rule,start=791),s)['summary']) for s in ('ordinary','adverse')}
    D.dump(I.HERE/'paper-parity.json',dict(completed_bar_signals_checked=checked,signal_mismatches=0,
          existing_expiry_ast_unchanged_except_quote_plumbing=True,sensitivity=sensitivity,
          forward_basis='SAMPLED_10S_FORWARD with actual depth, fresh next observations, >=12 complete bars and per-trade realized peak; not historical execution parity'))
    print('PAPER_PURE_SIGNAL_PARITY',checked,'bars, zero mismatches; existing money/policy AST identical')
    print('FORWARD_BASIS_SENSITIVITY',sensitivity)


if __name__=='__main__':main()
