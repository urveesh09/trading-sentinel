"""Versioned post-score reporting adapter. No strategy or frozen result changes."""
from pathlib import Path
import argparse,json
import runner8,forward8,score8

def normalize(report):
    for item in report.values():
        item['qualified']=False
        if item['eligible']==0:
            item['net']={'ordinary':None,'adverse':None}
            item['verdict']='DATA UNAVAILABLE' if item['missing'] else 'NOT EVALUATED'
        elif item['eligible']<40 or item['support']<20:
            item['verdict']='INCONCLUSIVE — support; no automatic promotion'
    return report

def practical_scores(results):
    out={}
    for key,h in results['hypotheses'].items():
        decision='NO PROMOTION'
        if key not in results['arms']:decision='DATA UNAVAILABLE'
        else:
            arm=results['arms'][key]
            if h['status'].startswith('TAIL SCREEN') and arm['wallet|ordinary']['halted']:
                decision='REJECT FOR CONTINUOUS WALLET — drawdown brake reached'
            elif key=='EN87|NIFTY':decision='FORWARD COMPARISON ONLY — positive development economics, unproven edge'
        out[key]=dict(frozen_screen_status=h['status'],practical_review=decision,qualified=False)
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ledger',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();dest=a.out.resolve();dest.relative_to(runner8.HERE)
    if a.ledger:
        data=normalize(runner8.review(forward8.Ledger(a.ledger)))
    else:data=practical_scores(json.loads((runner8.HERE/'results8.json').read_text()))
    score8.write(dest,data);print('REVIEW SAVED',len(data),'cells; unavailable money is null; no promotion')

if __name__=='__main__':main()
