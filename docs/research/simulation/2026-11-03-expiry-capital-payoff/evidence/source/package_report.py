"""Reconcile diagnostic cash and derive the report from immutable score files."""
from dataclasses import replace
import json,platform,sys
import numpy as np
import payoff_audit as A
import ledger_guard as G
import ledger_lab as K
import credit_lab as C
import hybrid_lab as H

def diagnostic_audit(ts):
    raw=json.loads((G.HERE/'diagnostics.json').read_text())['runs'];out={};original=C.leg_price
    def friction(t,i,j,buy,scenario,mark=False):
        p=original(t,i,j,buy,scenario,mark)
        if p is None or mark:return p
        p=K.E.up(p*1.01+.05) if buy else K.E.down(p*.99-.05)
        return p if p>0 else None
    try:
        for key,old in raw.items():
            label,brakes,basis,sc=key.split('|');rule=C.CreditRule(**old['rule'])
            C.leg_price=friction if label=='EXTRA_FRICTION' else original
            tt=ts[2024]+ts[2025] if basis=='continuous' else ts[int(basis)]
            new=(C.run if brakes=='True' else H.credit_unbraked)(tt,rule,sc,True);assert old==new
            proof,_=A.financial(old,tt,'diagnostic',rule);out[key]=proof
    finally:C.leg_price=original
    G.save('diagnostic-audit.json',dict(histories=len(out),runs=out,mismatches=0,selection=False))

def table(runs,names,basis='continuous'):
    rows=['| Model | Ordinary net | Worse fills | Severe fills | Worst ordinary day | Realized drawdown | Ordinary fees |',
          '|---|---:|---:|---:|---:|---:|---:|']
    for name in names:
        s=runs[f'{name}|{basis}|ordinary']['summary'];a=runs[f'{name}|{basis}|adverse']['summary'];z=runs[f'{name}|{basis}|catastrophe']['summary']
        rows.append(f"| {name} | {s['net']:,.2f} | {a['net']:,.2f} | {z['net']:,.2f} | {s['worst']:,.2f} | {s['drawdown']:,.2f} | {s['fees']:,.2f} |")
    return '\n'.join(rows)

def main():
    G.verify();ts=K.tapes();diagnostic_audit(ts)
    led=json.loads((G.HERE/'ledger-results.json').read_text());credit=json.loads((G.HERE/'credit-results.json').read_text())['runs']
    hybrid=json.loads((G.HERE/'hybrid-results.json').read_text())['runs'];unbraked=json.loads((G.HERE/'unbraked-results.json').read_text())['runs']
    base=led['runs'];allruns={**base,**credit,**hybrid};audit=json.loads((G.HERE/'audit-results.json').read_text());decisions={}
    for name in ('NET_RISK_LEDGER','PROFIT_REENTRY','CREDIT_8M','CREDIT_TREND','HYBRID_8M','HYBRID_TREND'):
        r=allruns[f'{name}|continuous|ordinary'];b=base['E031|continuous|ordinary'];delta=[x['net']-y['net'] for x,y in zip(r['days'],b['days'])]
        checks=dict(positive_each_year=all(allruns[f'{name}|{y}|{sc}']['summary']['net']>0 for y in (2024,2025) for sc in ('ordinary','adverse')),
          beats_each_year=all(allruns[f'{name}|{y}|{sc}']['summary']['net']>base[f'E031|{y}|{sc}']['summary']['net'] for y in (2024,2025) for sc in ('ordinary','adverse')),
          beats_continuous=all(allruns[f'{name}|continuous|{sc}']['summary']['net']>base[f'E031|continuous|{sc}']['summary']['net'] for sc in ('ordinary','adverse')),
          positive_ex_best_each_year=all(allruns[f'{name}|{y}|{sc}']['summary']['without_best']>0 for y in (2024,2025) for sc in ('ordinary','adverse')),
          positive_increment_ex_largest=sum(delta)-max(delta)>0,
          severe_drawdown_within_research_limit=allruns[f'{name}|continuous|catastrophe']['summary']['drawdown']<=5000,
          ordinary_drawdown_within_research_limit=r['summary']['drawdown']<=5000,
          no_unresolved=all(allruns[f'{name}|{basis}|{sc}']['summary']['unresolved']==0 for basis in ('continuous','2024','2025') for sc in ('ordinary','adverse','catastrophe')))
        decisions[name]=dict(checks=checks,increment=round(sum(delta),2),increment_ex_largest=round(sum(delta)-max(delta),2),
          primary_verdict='REJECTED_NO_IMPROVEMENT',native_candidate=False,margin_execution_qualified=False,
          credit_margin_required=name not in ('NET_RISK_LEDGER','PROFIT_REENTRY'))
        assert not all(checks.values())
    G.save('decisions.json',dict(primary=decisions,selected_candidate=None,qualification=False,protected_exam_read=False))
    verification=dict(python=platform.python_version(),numpy=np.__version__,offline=True,network_attempts=audit['network_attempts'],
      commands=[dict(command='python -m pytest python-engine/tests/test_expiry_e02.py python-engine/tests/test_expiry_e03.py python-engine/tests/test_expiry_e031.py <run>/test_ledger.py <run>/test_credit.py <run>/test_hybrid.py -q',exit_code=0,result='49 passed in 4.57s'),
       dict(command='python scripts/build_system_code_atlas.py; git diff --exit-code -- docs/SYSTEM_CODE_ATLAS.md',exit_code=0,result='295 modules; atlas byte-equivalent'),
       dict(command='python -m py_compile / compileall of new research files',exit_code=0),
       dict(command='python payoff_audit.py',exit_code=1,result='Temporary prefix id cache collision; retained, corrected in frozen v2'),
       dict(command='python payoff_audit_v2.py',exit_code=0,result='108 exact histories, 54 uncached prefixes, 1037 native long replays, 991 credit positions'),
       dict(command='python package_report.py diagnostic_audit',exit_code=0,result='60 additional diagnostic histories exact; cash/native fee identities checked')],
      full_engine_suite_rerun=False,reason='No native source changed; focused policies and admission/accounting changes checked',
      source_changes='Research only; current fees/lot normalized; native settings/schema/flags/actual capital unchanged',production_edited=False,download_calls=0,year2023_read=False)
    G.save('verification.json',verification)
    money=lambda r:f"{r['summary']['net']:,.2f}"
    rows=[]
    for name in ('E031','NET_RISK_LEDGER','PROFIT_REENTRY','CREDIT_8M','CREDIT_TREND','HYBRID_8M','HYBRID_TREND'):
        rows.append(f"| {name} | "+' | '.join(money(allruns[f'{name}|{y}|{sc}']) for y in (2024,2025) for sc in ('ordinary','adverse'))+' |')
    yearly='\n'.join(['| Model | 2024 ordinary | 2024 worse | 2025 ordinary | 2025 worse |','|---|---:|---:|---:|---:|',*rows])
    text='''# Expiry: capital reuse and directional payoff investigation

No new strategy generation earned implementation. **E03.1 remains the latest
implemented expiry research candidate**, with its Dev paper switch off. Six new
alternatives were frozen in three rounds, scored and rejected. No native engine,
configuration, schema, flag, actual risk, Production or download changed.

The owner explicitly widened research risk authority. I tested whether daily
turnover restrictions, the two-ticket limit, or the option payoff itself blocked
earnings. These are distinct from another exit-parameter search, the earlier
fixed-time/quiet-day iron butterfly, and the earlier extra-lot/size studies.

## Scope and interpretation

105 selected NIFTY expiry-minute tapes: 52 in 2024 and 53 in 2025. Both years
were already used repeatedly to design earlier versions. These are seen-year
counterfactuals, not validation or actual historical returns. No 2023 or original
fresh-data exam price was opened. SENSEX/full 2026 chain tests are unavailable in
this frozen set. Minute OHLC cannot qualify an instant-entry/microsecond edge.

Each arm starts with its own 25,000 cash; current 65-unit lots and current native
NFO costs normalize comparisons. Continuous 2024-to-2025 cash and reset-year
experiments are separate. Severe uses each next bar's high to buy/low to sell;
this changes which orders fill, so it is a stress scenario, not a monotone
same-trade haircut. Twenty-percent bar-volume capacity and estimated spreads
are proxies, not executable depth. These books are not Sentinel system profit.

## Three rounds

1. NET_RISK_LEDGER frees returned principal and removes two-ticket/gross-spend
   limits, while realized daily cash minus the full new ticket reserve must stay
   above the funded daily loss allowance. PROFIT_REENTRY uses positive closed
   profits only after the original first two tickets. Neither uses paper peak
   gains to fund entry. Original signal, contract and E03.1 exits stay fixed.
2. CREDIT_8M / CREDIT_TREND use the same trend-pullback direction to sell the
   first opposite-side OTM option and buy protection 50 points farther away.
   This makes money on a modest favorable move or decay rather than requiring
   an exploding cheap option. Eight-minute and underlying-thesis hold policies
   are the two frozen primary arms. Entries end at 15:00, flat trigger 15:14.
3. HYBRID_8M / HYBRID_TREND keep the original cheap-ticket eligibility. A plan
   with multiple lots retains E03.1; only an eligible one-lot plan can become
   credit, if funded at decision. A failed next-bar credit fill cannot fall back
   to a long based on the observed result. All positions share one sequential
   cash/risk/cooldown ledger within that arm.

Credit/hybrid daily original risk reserve is 5,000 instead of 2,500, with the
same inherited 1,500/3,000/4,000 cash drawdown brakes. The user did not impose
these research caps; I chose them before scoring. Rejection does not depend on
the caps: no new primary alternative beats E03.1 in both reset years.

## Continuous-book money (rupees after model fees)

'''+table(allruns,('E031','NET_RISK_LEDGER','PROFIT_REENTRY','CREDIT_8M','CREDIT_TREND','HYBRID_8M','HYBRID_TREND'))+'''

Realized drawdown is from day-close cash peaks; it is not intraday NAV. For
ordinary fills the independently reconstructed complete-bar NAV drawdowns were
1,838.85 for E03.1, 1,741.67 for HYBRID_8M and 2,397.96 for HYBRID_TREND.
The eight-minute hybrid's lower sampled NAV drawdown comes with much less profit;
it is not an income improvement. No missing NAV marks occurred in primary runs.

## Reset-year experiments (do not add these to continuous-book money)

'''+yearly+'''

The ledgers add no ordinary/worse-fill tickets at all: all three still take 41
over the two years. NET worsens severe fills to -3,599.64 versus -3,234.08.
Here the original cash/entry limits are not the earnings bottleneck.

E03.1 ordinary net excluding its best day is 6,576.75. HYBRID_8M leaves 1,255.64
and HYBRID_TREND 2,544.88. HYBRID_8M's 2024 reset turns negative without its best
day; HYBRID_TREND's 2025 reset does too. Every new continuous increment excluding
its largest incremental day is nonpositive. Full checks: decisions.json.

## Do inherited brakes hide a good credit strategy?

No. With no drawdown brakes, but cash/collateral and funded daily risk still
binding, CREDIT_8M takes 44 ordinary tickets and loses 2,630.64; CREDIT_TREND
takes 44 and loses 1,496.99. Their ordinary fees are 4,362.89 and 4,356.99.
The 8-minute version makes 1,732.25 before fees but loses after fees. Without
brakes HYBRID_8M stays 7,105.60 and HYBRID_TREND drops to 7,486.10.

Fixed controls do not supply a replacement. Unbraked adverse reverse-direction
credit loses 7,979.34; 6/10-minute holds lose 5,217.62 / 5,395.30. Additional
one-percent-plus-tick friction loses 3,962.30. A 100-point hedge barely trades
(one continuous trade, none in the 2025 reset) because its full reserve rarely
fits the daily cap. That result establishes limited feasibility, not a broad
claim that wide spreads cannot work. All 60 diagnostic histories are retained.

## What the losses and winners teach

- The original one-lot positions earned 6,858.27 over 31 ordinary tickets.
  They were not dead weight just because they cannot leave a partial runner.
  Nine two-lot positions earned 5,121.72 and one three-lot position earned 446.72.
  This is attribution on seen data, not a new lot-count trading filter.
- A trend view does not automatically transfer between payoffs. Credit changes
  which strike is exposed, caps favorable gains, needs a hedge and four orders,
  and faces a different losing path. Its upfront receipt is not earned profit.
- E03.1's 41 ordinary tickets included 20 negative tickets. Nine stopped; nine
  ended negative on the eight-minute clock, one by underlying structure and two
  by a trail (one position may be counted only by its final exit below). Exact
  per-position cash is in trades.csv and full events in ledger-results.json.
  A stop/trail trigger is followed by a later fill and cannot guarantee its price.
- Several high-return days remain influential. Credit does not discover new
  hero moves; it gives up the convex long-option gain on replaced positions.
- Faster polling has no measured profit here. Without timestamped bid/ask depth,
  order-arrival, partial-fill and cancellation evidence, treating a price jump
  as an earlier executable order would invent the edge being sought.

The loss-count sentence above is generated precisely in loss-attribution.json;
use its mutually exclusive final-exit totals when discussing ticket counts.
No inference that *all* market jumps come from a named participant or a unique
cause follows from these OHLC/OI files. Earlier skeletal bootstrap loss-year
percentages are conditional model outputs, not calibrated future probabilities.

## Execution, margin and residual assets

Vertical terminal loss is bounded by strike width less credit before costs.
That accounting identity is described by [Zerodha Varsity](https://zerodha.com/varsity/chapter/bull-put-spread/)
and the [Options Industry Council](https://www.optionseducation.org/strategies/all-strategies/bear-call-spread-credit-call-spread).
Neither establishes an intraday fill or an Indian broker margin requirement.
[NSE's margin rules](https://www.nseindia.com/static/products-services/equity-derivatives-margins)
use SPAN and additional margin components. Historical broker SPAN/ELM, atomic
basket execution and queue positions were not available here.

The model therefore requires full width plus liquidation/fee buffer in own cash
and explicitly reports margin/execution as UNQUALIFIED. A losing cash-only model
does not need optimistic broker leverage to be rejected. Shorts are closed first;
an unsellable fully paid long hedge would be retained as a zero-lower-bound asset
with assumed writeoff separate from realized fills. An unclosed short halts the
book and makes following dates unavailable. No such residual/unresolved exposure
occurred in the 108 primary/control histories or 60 fixed diagnostics.

## Verification and reproducibility

- Freezes committed before their scores: f34ceb9 ledger, ff34d6b credit,
  2d0fe98 hybrid, 698a128 diagnostics. Sources/rules/results remain immutable.
- The ledger baseline reproduces 99 independent-year position/event histories
  across fills (an earlier progress note called these histories imprecisely).
  Hybrid control reproduces baseline day cash and complete original events.
- 108 primary/control histories replay exactly; 1,037 repeated long positions
  match shipped E03.1 actions/fees, 991 credit positions reconcile leg cash/fees,
  reserves and clocks; 54 actual input prefixes rebuild without future readings.
  Another 60 diagnostic histories independently reconcile. These repetitions
  are verification coverage, not independent statistical samples.
- Original prefix audit exited 1: the old research cache keyed temporary objects
  by Python id, which can be reused. Source/error retained. Frozen v2 uses the
  uncached original signal for prefixes and checks cached full signals against it;
  primary scores unchanged. Full scored tapes stay alive, so that collision did
  not contaminate these scores. No native engine cache was changed.
- 49 focused checks pass; new Python compiles; regenerated 295-module atlas is
  unchanged. Full engine suite was not rerun because native code did not change.
- ledger_guard.py verifies selected DBs, 713 older/source evidence hashes, exact
  owner documentation suffixes and Production identity/diff after each commit.
  Python 3.11.9 / NumPy 1.26.4; offline scoring; no provider calls or 2023 read.

Commands from the run folder (use python-engine/winvenv/Scripts/python.exe):
ledger_study.py score; credit_study.py score; hybrid_study.py score;
payoff_diagnostics.py score; payoff_audit_v2.py; package_report.py.
Score files are append-only: rerunning a completed score intentionally refuses
to overwrite. Audit functions replay and compare existing results instead.
Raw chosen-year SQLite inputs remain ignored in the earlier E02 _local folder;
hashes/required dependency locations are in initial.json and evidence/data-proof.json.

## Decision and remaining work

No E03.2 or increased live risk is justified by this round. E03.1 itself remains
a seen-year paper hypothesis and loses under severe fills. No generation name
can make that evidence stronger. Keep the frozen fresh-data family exam intact
and gather genuinely new executable paper outcomes before increasing size.
If researching execution next, test decision-to-fill prices/quote age/fees on
new timestamped quotes and compare rejected orders too; record fast orders before
evaluating them. No current finding warrants changing the trading engine.

Dev research is committed/pushed through the receipts recorded in STATUS.md and
completion-receipt.json. Production, N11, A/B/C/D and native E variants are
unchanged; no migration or rollout is needed. Research rollback is stopping this
isolated lab. Sealed receipts: evidence/REPORT.md, with pinned verification after
later documentation commits. Passing receipts/tests verify mechanics and hashes,
not future profitability or partner qualification.
'''
    ps=[p for d in base['E031|continuous|ordinary']['days'] for p in d['positions']]
    from collections import Counter
    losses=Counter(p['events'][-1]['reason'] for p in ps if p['net']<0)
    G.save('loss-attribution.json',dict(negative_tickets=sum(losses.values()),final_exit_counts=dict(losses),
      losses=[dict(day=p['day'],net=p['net'],reason=p['events'][-1]['reason']) for p in ps if p['net']<0]))
    start=text.index('- E03.1\'s 41 ordinary tickets included')
    end=text.index('- Several high-return days',start)
    counts=', '.join(f'{n} {why}' for why,n in sorted(losses.items()))
    text=text[:start]+f"- E03.1's 41 ordinary tickets included {sum(losses.values())} negative tickets,\n  classified by final exit: {counts}. A stop/trail\n  trigger is followed by a later fill and cannot guarantee its price. Exact\n  ticket cash/events are retained; no loss is excluded from the books.\n"+text[end:]
    text=text.replace('The loss-count sentence above is generated precisely in loss-attribution.json;\nuse its mutually exclusive final-exit totals when discussing ticket counts.\n','Final-exit counts are mutually exclusive (loss-attribution.json).\n')
    report=G.ROOT/'docs/EXPIRY_RESEARCH_CAPITAL_PAYOFF.md';assert not report.exists();report.write_text(text,encoding='utf-8')
    (G.HERE/'README.md').write_text('# Capital/payoff expiry study\n\nSee [plain report](../../../EXPIRY_RESEARCH_CAPITAL_PAYOFF.md), immutable PLAN/CREDIT/HYBRID contracts, STATUS.md and [stock receipts](evidence/REPORT.md).\n\nSix primary alternatives rejected; all scores are seen-year normalized bar models. Run payoff_audit_v2.py to replay existing primary books without overwriting them. package_report.py records additional diagnostic reconciliation and produces the report; its outputs are append-only. Raw data stay ignored; initial.json binds required selected-year files.\n',encoding='utf-8')
    print('REPORT_CREATED; 60 additional diagnostic histories audited; six alternatives rejected')

if __name__=='__main__':main()
