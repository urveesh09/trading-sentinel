"""Post-search independent ledger audit and descriptive report, never a selector."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timedelta, date
import hashlib
import importlib.util
import json
from pathlib import Path
import pickle
import random
import statistics
import subprocess
import sys

P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('o27e_report_lab',P/'lab.py')
lab=importlib.util.module_from_spec(spec);sys.modules[spec.name]=lab;spec.loader.exec_module(lab)
from fno_costs import calc_fno_costs


def read(name): return json.loads((P/name).read_text())
def cash(x): return f'{x:,.2f}'


def audit():
    results=read('results.json');frozen=read('freeze.json')
    assert results['freeze_sha256']==lab.grid._sha(P/'freeze.json')
    assert frozen['bindings']==lab.bindings()
    reports=[results['control'],*results['candidates'],*results['strict_diagnostics']]
    observations={}
    for f in (P/'_local/cache').glob('*.pkl'):
        rows,_=pickle.loads(f.read_bytes());observations[f.stem]=rows
    checks=[];financial_count=0
    for report in reports:
        label='CURRENT' if report['genome'] is None else lab.digest(report['genome'])
        if report['strict_bid_depth_diagnostic']: label+=' STRICT'
        crossed=[];fees=0.;independent_net=0.
        for t in report['trades']:
            if 'net_pnl' not in t: continue
            at=datetime.fromisoformat(t['entry_time']);end=datetime.fromisoformat(t['exit_time'])
            assert end>=at
            assert datetime.fromisoformat(t['bar_ts'])+timedelta(minutes=5)<=at.replace(tzinfo=None)
            assert at.date().isoformat() not in read('calendar.json')['nifty_expiries_in_window']
            assert 585<=at.hour*60+at.minute<885
            qty=t['entry_qty'];gross=(t['exit_premium']-t['entry_premium'])*qty
            fee=calc_fno_costs(t['entry_premium'],t['exit_premium'],qty)
            assert not t['fills'], 'Unexpected partial/add-on: independent audit needs its accounting'
            assert abs(t['gross_pnl']-gross)<.011
            assert abs(t['net_pnl']-(gross-fee))<.011
            rows=observations[at.date().isoformat()]
            entry=next(o for o in rows if o.at==at);exit_obs=next(o for o in rows if o.at==end)
            eq=next(q for q in entry.options.values() if q.contract.tradingsymbol==t['tradingsymbol'])
            xq=next(q for q in exit_obs.options.values() if q.contract.tradingsymbol==t['tradingsymbol'])
            assert abs(t['entry_premium']-eq.ask)<.00011
            assert abs(t['exit_premium']-(xq.bid if xq.bid>0 else xq.ltp))<.00011
            if report['strict_bid_depth_diagnostic']:
                assert xq.bid>0 and xq.bid_quantity>=qty
                assert min(eq.bid_quantity,eq.ask_quantity)>=int(lab.settings.FNO_MAX_LOTS)*eq.contract.lot_size
            for a,b in zip(rows,rows[1:]):
                if (b.at-a.at).total_seconds()>180 and at<b.at and end>a.at:
                    crossed.append({'symbol':t['tradingsymbol'],'entry':t['entry_time'],'exit':t['exit_time'],
                                    'gap_seconds':round((b.at-a.at).total_seconds(),3)})
            independent_net+=gross-fee;fees+=fee;financial_count+=1
        assert abs(independent_net-report['metrics']['net'])<max(.02,len(report['trades'])*.011)
        checks.append({'arm':label,'independent_net':round(independent_net,4),'charges':round(fees,4),
                       'closed':report['metrics']['trades'],'unresolved':report['metrics']['unresolved'],
                       'holds_crossing_recording_gaps':crossed,'all_checked':True})
    # Check every searched arm's own metric totals; finalists also get full quote/fee checks above.
    for f in (P/'_local/A').glob('*.json'):
        row=json.loads(f.read_text());dates=list(row['metrics']['daily'])
        assert row['metrics']==lab.metrics(row['trades'],dates)
    initial=read('_local/preflight-state.json')
    prod='C:/Users/Urveesh/Desktop/Production_Trading-sentinel'
    sha=subprocess.check_output(['git','-C',prod,'rev-parse','HEAD'],encoding='utf-8').strip()
    status=subprocess.check_output(['git','-C',prod,'status','--porcelain'],encoding='utf-8')
    assert sha==initial['production_sha'] and status==initial['production_status']
    return {'financial_trade_checks':financial_count,'reports':checks,'search_metric_checks':len(results['evaluations']),
            'source_and_dataset_bindings_valid':True,'production_git_sha_and_status_unchanged':True,
            'production_sha':sha,'actual_orders':0,'coverage':read('_local/coverage.json')}


def interval(values,seed=917):
    """Post hoc descriptive block bootstrap; not a prediction or selection test."""
    rng=random.Random(seed);n=len(values);means=[]
    for _ in range(3000):
        sample=[]
        while len(sample)<n:
            i=rng.randrange(n);sample.extend(values[(i+j)%n] for j in range(3))
        means.append(sum(sample[:n])/n)
    means.sort();return [round(means[74],2),round(means[2924],2)]



def learning(r,selection,summary):
    """Descriptive interpretation only; never feeds the frozen selector."""
    return [
        '1. **More modeled profit did not establish better consistency.** Efficiency break earned INR 31,063.33 versus 10,801.09 for the shipped control, but closed-trade drawdown rose from 1,990.89 to 6,748.74. Net divided by that drawdown fell from 5.43 to 4.60. Its later seen-period drawdown exceeded the frozen INR 5,000 cap; do not promote it.',
        '2. **The useful hypothesis is a local trend-quality filter.** The selected candidate requires a new break of the preceding four completed 5-minute bars, a 0.2-ATR buffer, path efficiency >=0.35, candle body fraction >=0.55 and relative volume >=1.2. It adds no VWAP direction gate. The planner uses the tighter structural/2-ATR stop, 1.8R target and LOOSE exit (60-minute limit, 1.5-ATR trail, profit lock off). The inherited regime, risk and expiry gates remain. Whether the local channel or the looser exit contributes the edge needs a separately frozen ablation; this search cannot assign causation.',
        '3. **Some neighbours survive, but the region is fragile.** These are A-only one-gene changes, never later-period retunes: reducing RVOL 1.2 to 1.0 changes net from +12,192.74 to -8,230.54; changing LOOSE to PATIENT gives -8,842.66. Other neighbours remain profitable: lookback 4 to 6 gives +10,487.66; body 0.55 to 0.35 gives +17,400.59; target 1.8R to 2.4R gives +14,047.33. The complete neighbour-median fitness is -0.827. This is not a broad robust plateau.',
        '4. **Profitable often is not profitable every day.** Efficiency has 21 winning trades out of 38 (55.3%) and 12 green / 7 red / 19 active recorded sessions. That is 63.2% of active sessions, or 41.4% of all 29 archived sessions. Ten sessions have no modeled close; missing September 18 is unknown. The control has 6 green / 4 red / 10 active sessions. These are descriptive frequencies, not estimated future success rates.',
        '5. **Costs alone do not explain the failure.** Efficiency remains +25,034.53 under the frozen extra-cost arithmetic, and +22,655.57 after removing its best day. Removing its single best trade leaves +23,207.97 (control +3,693.42; compression -6,735.87). Nevertheless, risk failure, parameter sensitivity and a paired daily-difference interval crossing zero remain.',
        '6. **Keep unsuccessful families in the record.** Of 121 evaluated genomes, 46 earn positive A net but only seven pass all A criteria. Failed-auction reversal has no eligible arm. The frozen compression leader is already ineligible on A and loses 5,936.52 on B; one eligible compression neighbour is not substituted after selection. This rejects these tested configurations, not every possible reversal/compression strategy.',
        '7. **Next useful work is fresh evidence and recording quality.** Keep the shipped rules and the existing six-arm O27c panel unchanged. Repair/archive quote coverage through a separate engineering change, especially continuous bid/depth and intratrade marks. If the owner chooses a prospective comparison, register the exact candidate, control, sample horizon, drawdown/cost gates and stopping rules before collecting new sessions; no daily retuning or early winner declaration. No amount of additional tuning on these dates creates untouched validation.',
        '8. **Evidence-helper limitation is preserved.** The supplied helper binds the initial Git HEAD as well as source hashes. Committing the required pre-score freeze legitimately changed HEAD, so its generated REPORT is INVALID for that metadata mismatch. Its failure is retained; no frozen receipt/helper is rewritten. The separate verify_study.py checks ancestor commits, every frozen input/source hash, raw-data bindings, report integrity and ledger arithmetic without claiming that the original helper passed. Neither audit certifies future profitability.'
    ]

def render():
    r=read('results.json');selection=read('selection.json');proof=audit()
    lab.write_new(P/'audit.json',proof)
    control=r['control'];candidates=r['candidates'];arms=[control,*candidates]
    labels=['Shipped control',*[x['genome']['family']+' '+lab.digest(x['genome']) for x in candidates]]
    searched=list(r['evaluations'].values())
    # Distinct trade histories expose neutral/duplicate parameter paths honestly.
    outcomes=set()
    for f in (P/'_local/A').glob('*.json'):
        row=json.loads(f.read_text());outcomes.add(lab.digest(lab.signature(row['trades'])))
    summary={'genomes':len(searched),'distinct_A_trade_histories':len(outcomes),
             'profitable_A_genomes':sum(x['metrics']['net']>0 for x in searched),
             'eligible_A_genomes':sum(x['eligible'] for x in searched),
             'families':{fam:{'evaluated':sum(x['genome']['family']==fam for x in searched),
                              'eligible':sum(x['eligible'] and x['genome']['family']==fam for x in searched)} for fam in lab.FAMILIES},
             'finalists':[], 'verdict':r['verdict']}
    for candidate in candidates:
        days=list(control['metrics']['daily'])
        paired=[candidate['metrics']['daily'][d]-control['metrics']['daily'][d] for d in days]
        summary['finalists'].append({'genome':candidate['genome'],'B_checks':candidate['B_checks'],
            'all_B_checks_pass':all(candidate['B_checks'].values()),
            'posthoc_paired_daily_difference_95pct_block_bootstrap':interval(paired)})
    lab.write_new(P/'summary.json',summary)
    lines=['# O27e: learning from novel F&O entry-family evolution','',
           '**Verdict: exploratory research only. No untouched validation; keep the shipped book.**','',
           'Study date: 2026-10-27. Frozen source commit: `3e2bcfe`. All dates are previously seen.',
           'NIFTY single-leg portfolio proxy only; results must not be summed with other books.','',
           '## What was actually run','',
           f'- {len(lab.FAMILIES)} new entry families; {summary["genomes"]} distinct genomes, including one-step neighbours.',
           f'- {summary["distinct_A_trade_histories"]} distinct development-period trade histories; parameter combinations are not independent experiments.',
           '- Three separate populations of eight, five generations; tournament selection, uniform crossover, 18% per-gene mutation, elites and immigrants.',
           '- Search: Sep 10–Oct 9, 19 archived sessions. Two family leaders frozen before Oct 12–26 diagnostics (10 sessions, also seen).',
           '- New predicates relative to O27/O27b: efficiency-filtered rolling break, compressed rolling-range release and opening-range failed-auction reversal.',
           '- Shared planner, options selection, costs, sizing, risk brakes and exit ladder reused. No runtime source changes.',
           '- The previous CURRENT receipt reproduces exactly; 14 new synthetic checks and 43 existing F&O regressions passed before scoring.','',
           '## Full-window priced-close results','',
           'These are modeled outcomes of recorded quotes, not actual executions. Unresolved positions have no invented sale or P&L.',
           'Drawdown is on closed-trade P&L; it excludes intratrade marked losses.','',
           '| Arm | Closed / unresolved | Net INR | Charges INR | Win rate | PF | Closed-trade DD INR | Net minus best day | Fixed-trade stressed net |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for label,arm in zip(labels,arms):
        m=arm['metrics'];wr='n/a' if m['win_rate'] is None else f'{100*m["win_rate"]:.1f}%'
        pf='n/a' if m['profit_factor'] is None else f'{m["profit_factor"]:.2f}'
        lines.append(f'| {label} | {m["trades"]} / {m["unresolved"]} | {cash(m["net"])} | {cash(m["charges"])} | {wr} | {pf} | {cash(m["drawdown_closed_trades"])} | {cash(m["net_without_best_day"])} | {cash(m["stressed_net_fixed_trades"])} |')
    lines += ['','Fixed-trade stress subtracts INR 1 per option unit on each side and adds 25% to charges. It holds the trade list fixed; sizing, gates and halts are not resimulated.','',
              '## Search versus later seen-data diagnostics','',
              '| Family | Genomes evaluated | Eligible on A |','|---|---:|---:|']
    for fam,m in summary['families'].items():lines.append(f'| {fam} | {m["evaluated"]} | {m["eligible"]} |')
    lines += ['','| Frozen finalist | A net | A trades | Neighbour median fitness | B net | B trades / unresolved | B checks |','|---|---:|---:|---:|---:|---:|---|']
    for arm,chosen in zip(candidates,selection['candidates']):
        a=chosen['metrics'];b=arm['B_seen_diagnostic'];checks=arm['B_checks']
        lines.append(f'| {arm["genome"]["family"]} | {cash(a["net"])} | {a["trades"]} | {chosen["plateau"]:.3f} | {cash(b["net"])} | {b["trades"]} / {b["unresolved"]} | '+(', '.join(k+'='+str(v) for k,v in checks.items()))+' |')
    lines += ['','B is not an untouched holdout. It was inspected by earlier agents, and late-October days motivated prior ideas. A positive B diagnostic cannot certify an edge.','',
              '## Exact finalist genomes','']
    for label,arm in zip(labels[1:],candidates):
        lines += [f'### {label}','','```json',json.dumps(arm['genome'],indent=2),'```','']
    lines += ['## Execution sensitivity and recording gaps','',
              '| Arm | Strict closed / unresolved | Strict priced net | LTP exits (primary) | Insufficient entry / exit depth (primary) |',
              '|---|---:|---:|---:|---:|']
    for label,primary,strict in zip(labels,arms,r['strict_diagnostics']):
        m=strict['metrics'];e=primary['execution']
        lines.append(f'| {label} | {m["trades"]} / {m["unresolved"]} | {cash(m["net"])} | {e.get("ltp_exits",0)} | {e.get("entry_depth_insufficient",0)} / {e.get("exit_depth_insufficient",0)} |')
    lines += ['','Strict diagnostics require both-sided displayed depth for maximum allowed lots at entry, and a positive bid covering the held quantity at exit. They can change admissions and book history; they are an execution-sensitivity scenario, not exact live parity.','',
              '- Archive: 29 of 30 expected exchange sessions. September 18 is unavailable, never assigned zero profit.',
              '- Eight recorded sessions contain gaps longer than 180 seconds. October 13 has an approximately 95-minute gap; October 16 ends around 10:08 IST.',
              '- Every day is retained. The audit lists each closed hold crossing a recording gap; there are no interpolated quotes or perfect intragap stops.',
              '- NSE expiry policy/holiday circular independently confirm the six expiry dates in the study, including October 19. Contract lot/token details still come from archived packets.',
              '- Sampling is about 60 seconds versus about 10 seconds live. Partial fills, queue position, broker rejection, shared capital reservations and a fully counterfactual spread book are not reproduced.','',
              '## Supplemental uncertainty diagnostic','',
              'Post hoc descriptive 3-session moving-block bootstrap, 3,000 draws, fixed seed; intervals are for mean daily candidate-minus-control P&L on these same seen observations. They are not a future-profit probability, a multiple-testing correction or a selection gate.','']
    for label,entry in zip(labels[1:],summary['finalists']):
        lo,hi=entry['posthoc_paired_daily_difference_95pct_block_bootstrap']
        lines.append(f'- {label}: INR {cash(lo)} to {cash(hi)} per archived session.')
    lines += ['','## Learning','',*learning(r,selection,summary),'',
              '## Independent checks and status','',
              f'- {proof["financial_trade_checks"]} closed-trade records checked against recorded entry asks, exit bids/LTP, quantity, fees, causal clocks and expiry restrictions.',
              f'- All {proof["search_metric_checks"]} searched-arm metric receipts reconcile to their trade lists.',
              '- Dataset/source hashes reverified after scoring. Production Git SHA/status unchanged; no broker calls, orders, runtime changes, deployments or new recurring tasks.',
              '- Existing unrelated Dev changes were preserved. Freeze and results are local research commits; no push or promotion is implied.',
              '- Original documentation check hit a Windows cp1252 decoding error; explicit UTF-8 recheck passed. No research rule changed.',
              '- Plot dependencies, if used, are installed only in this study’s ignored `_local/plot-packages`, not the shared venv.','',
              '## Daily modeled priced-close P&L','',
              '| Session | Shipped | Finalist 1 | Finalist 2 |','|---|---:|---:|---:|']
    for d in control['metrics']['daily']:
        lines.append('| '+d+' | '+' | '.join(cash(arm['metrics']['daily'][d]) for arm in arms)+' |')
    (P/'ANALYSIS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    lab.write_new(P/'chart-data.json',{'labels':labels,'days':list(control['metrics']['daily']),
        'daily':[[arm['metrics']['daily'][d] for d in control['metrics']['daily']] for arm in arms],
        'unresolved':[arm['metrics']['unresolved'] for arm in arms]})
    print(json.dumps(summary,indent=2))


if __name__=='__main__':render()
