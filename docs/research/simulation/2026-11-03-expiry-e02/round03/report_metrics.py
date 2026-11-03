"""Post-selection accounting. No rule selection or source-evidence alteration."""
import csv,json
from collections import defaultdict
import iterate as I
import data as D
import e02_lab as E


def marked(result,tapes):
    before=0.;peak=E.START_CASH;draw=0.;low=E.START_CASH;missing=observed=0
    for tape,row in zip(tapes,result['days']):
        for i in range(tape.n):
            pnl=before;valid=True
            for p in row['positions']:
                if i<p['entry_i']:continue
                if i>=p.get('exit_i',tape.n):pnl+=p['net'];continue
                q=tape.q[i,p['j']]
                if not E.np.isfinite(q).all() or q[4]*.2<65:valid=False;break
                bid=E.down(float(q[3])-E.half(float(q[3])))
                if bid<=0:valid=False;break
                pnl+=(bid-p['entry'])*65-p['events'][0]['fees']-E.fee(bid,65,False)
            if valid:
                value=E.START_CASH+pnl;observed+=1;peak=max(peak,value);low=min(low,value);draw=max(draw,peak-value)
            else:missing+=1
        before+=row['net']
    return dict(sampled_marked_drawdown=round(draw,2),sampled_low_equity=round(low,2),observable_minute_marks=observed,unmarkable_minutes=missing,
                basis='Modelled close bid less whole-lot sale fees; sampled marks, not intrabar/depth/broker NAV')


def main():
    a=json.loads((I.HERE/'candidate-audit.json').read_text());tapes={y:D.load_year(y,exam=y==2024) for y in (2024,2025)}
    out=dict(marked={},trade_statistics={},fit_status='Both years seen; no independent qualification')
    for sc,row in a['continuous'].items():
        pp=[p for d in row['days'] for p in d['positions']];values=[p['net'] for p in pp]
        profit=sum(v for v in values if v>0);loss=-sum(v for v in values if v<0)
        out['trade_statistics'][sc]=dict(trades=len(values),wins=sum(v>0 for v in values),losses=sum(v<0 for v in values),
          trade_profit_factor=profit/loss if loss else None,worst_trade=min(values,default=None),net=round(sum(values),2),
          without_best_trade=round(sum(values)-max(values,default=0),2),fees=round(sum(p['fees'] for p in pp),2))
        if sc in ('ordinary','adverse'):out['marked'][sc]=marked(row,tapes[2024]+tapes[2025])
    rule=E.Rule(**a['rule']);out['lot_sensitivity']={};saved=E.LOT
    try:
        for lot in (25,50,75):
            E.LOT=lot
            out['lot_sensitivity'][str(lot)]={str(y):{s:I.run(t,rule,s)['summary'] for s in ('ordinary','adverse')} for y,t in tapes.items()}
    finally:E.LOT=saved
    with (I.HERE/'daily-results.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['scenario','date','net','fees','trades','reserved','unresolved','cash_after'])
        for s,r in a['continuous'].items():
            for d in r['days']:w.writerow([s,d['day'],d['net'],d['fees'],d['trades'],d['spent'],d['unresolved'],d['cash_after']])
    with (I.HERE/'trades.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['scenario','date','symbol','entry_minute_index','exit_minute_index','lots','price','net','fees','reserved','exit'])
        for s,r in a['continuous'].items():
            for d in r['days']:
                for p in d['positions']:w.writerow([s,p['day'],p['symbol'],p['entry_i'],p.get('exit_i'),p['lots'],p['entry'],p['net'],p['fees'],p['reserve'],p['events'][-1].get('reason')])
    D.dump(I.HERE/'metrics.json',out)
    print('POST_SELECTION_ACCOUNTING',out['trade_statistics'],out['marked'])


if __name__=='__main__':main()
