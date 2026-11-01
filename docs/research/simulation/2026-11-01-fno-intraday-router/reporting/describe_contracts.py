"""Post-run descriptive opportunity context, never used to choose a router."""
import json,re,statistics
from datetime import datetime
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
YEARS=('2024','2025','2026')


def run():
    rows=[]
    for y in YEARS:
        key=json.loads((HERE/f'_local/keys-base-{y}.json').read_text())['OLD_BREAKOUT_LOW']
        obj=json.loads((HERE/'_local/evals'/f'{key}.json').read_text())
        for t in obj['trades']:
            m=re.fullmatch(r'NIFTY(\d{6})(\d+)(CE|PE)',t['tradingsymbol']);assert m
            expiry=datetime.strptime(m[1],'%y%m%d').date();entry=datetime.fromisoformat(t['entry_time']);days=(expiry-entry.date()).days;assert days>=0
            minute=entry.hour*60+entry.minute
            rows.append({'year':y,'dte':days,'clock':'BEFORE11' if minute<660 else ('11_TO13' if minute<780 else 'FROM13'),
                         'direction':t['direction'],'net':t['net_pnl']-200.,'premium':t['entry_premium']})
    results={}
    for feature in ('dte','clock','direction'):
        results[feature]={}
        for value in sorted({r[feature] for r in rows}):
            results[feature][str(value)]={}
            for y in YEARS:
                part=[r for r in rows if r['year']==y and r[feature]==value]
                results[feature][str(value)][y]={'trades':len(part),'net':round(sum(r['net'] for r in part),2),'wins':sum(r['net']>0 for r in part),
                    'median_entry_premium':statistics.median([r['premium'] for r in part]) if part else None}
        for y in YEARS:assert abs(sum(v[y]['net'] for v in results[feature].values())-sum(r['net'] for r in rows if r['year']==y))<.05
    (HERE/'opportunity-context.json').write_text(json.dumps({'status':'POST_RUN_DESCRIPTIVE_ONLY_NOT_A_STRATEGY_TEST','records':len(rows),'used_in_routing':False,'partitions':results},indent=2)+'\n')
    print('OPPORTUNITY_CONTEXT_RECONCILED',len(rows))


if __name__=='__main__':run()
