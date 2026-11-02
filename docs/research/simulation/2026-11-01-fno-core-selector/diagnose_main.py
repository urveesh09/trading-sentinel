"""Descriptive incumbent/member/exposure audit; never a fitted selector."""
import json
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent;N01=HERE.parent/'2026-11-01-fno-intraday-router';BROAD=HERE.parent/'2026-10-31-fno-broad-search'
load=lambda p:json.loads(p.read_text())
YEARS=('2024','2025','2026');NAMES=('SHIPPED','OR20','EFF','TPB')


def stats(rows):
    net=sum(t['net_pnl'] for t in rows)
    return {'trades':len(rows),'net':round(net,4),'wins':sum(t['net_pnl']>0 for t in rows),'average_lots':sum(t['entry_qty']/65 for t in rows)/len(rows) if rows else None,
            'extra_cost':round(sum(t.get('extra_cost',0) for t in rows),4),'gross':round(sum(t['gross_pnl'] for t in rows),4),
            'exit_reasons':dict(Counter(t['exit_reason'] for t in rows))}


def run():
    out={'schema':'n02_incumbent_diagnosis_v1','status':'DESCRIPTIVE_SEEN_DATA_NOT_NEW_BACKTEST','years':{}}
    for y in YEARS:
        key=load(N01/f'_local/keys-base-{y}.json')['MAIN'];obj=load(N01/'_local/evals'/f'{key}.json');rows=obj['trades']
        record={'main':stats(rows),'members':{},'funnel_evaluations_not_unique_trades':obj['funnel']}
        for name in NAMES:
            part=[t for t in rows if NAMES[t['member']]==name]
            record['members'][name]={'all':stats(part),'directions':{d:stats([t for t in part if t['direction']==d]) for d in ('LONG','SHORT')}}
        assert abs(sum(v['all']['net'] for v in record['members'].values())-record['main']['net'])<.001
        rawkey=load(BROAD/f'_local/keys-screen-{y}.json')['RAW|MAIN'];raw=load(BROAD/'_local/evals'/f'{rawkey}.json')['trades']
        record['one_lot_diagnostic_after_extra200']={n:{'trades':sum(NAMES[t['member']]==n for t in raw),'net':round(sum(t['net_pnl']-200 for t in raw if NAMES[t['member']]==n),4)} for n in NAMES}
        k=load(N01/f'freshness/_local/keys-candidate-{y}.json')['EX|LEARN'];learner=load(N01/'freshness/_local/evals'/f'{k}.json')['trades']
        signature=lambda t:(t['bar_ts'],t['tradingsymbol'],t['direction'],t['entry_time'])
        mainkeys={signature(t) for t in rows};learnkeys={signature(t) for t in learner}
        record['earlier_selector']={'trades':len(learner),'exact_signal_entry_matches':len(mainkeys&learnkeys),'match_limit':'same opportunity/entry clock only; no paired P&L unless prices/quantities/exit also match',
            'macro_usage':{s:{'trades':sum(t['router_cell'].endswith(s) for t in learner),'net':round(sum(t['net_pnl'] for t in learner if t['router_cell'].endswith(s)),4)} for s in ('HIGH','LOW')}}
        out['years'][y]=record
    (HERE/'diagnosis.json').write_text(json.dumps(out,indent=2)+'\n');print('INCUMBENT_DIAGNOSIS_RECONCILED')


if __name__=='__main__':run()
