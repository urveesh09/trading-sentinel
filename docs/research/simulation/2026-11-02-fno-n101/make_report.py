"""Human-facing report from the fixed score and independent audits. No resimulation."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
DOCS=HERE.parents[2]


def money(v):
    return f'{v:,.0f}'


def main():
    result=json.loads((HERE/"results.json").read_text())
    identity=json.loads((HERE/"IDENTITY.json").read_text())
    audits=[json.loads((HERE/f"audit-{y}.json").read_text()) for y in ("2023","2024","2025","2026")]
    assert all(a["passed"] for a in audits)
    peak_audit=json.loads((HERE/"watch-peak-audit.json").read_text())
    assert peak_audit["passed_decision_bound"]
    checks={k:sum(a["checks"][k] for a in audits) for k in audits[0]["checks"]}
    names=("N08","CUSHION","STRICT","N10","WATCH_FLAT","PREMIUM_LOCK")
    labels={"N08":"N08","CUSHION":"N09.1","STRICT":"N10 one try","N10":"N10 retry","WATCH_FLAT":"N10.1 WATCH_FLAT","PREMIUM_LOCK":"N10.1 PREMIUM_LOCK"}
    books=result["books"]
    table='| Book | 2023 | 2024 | 2025 | 2026 to Oct 28 | Total |\n|---|---:|---:|---:|---:|---:|\n'
    for n in names:
        b=books[n]
        table+='| '+labels[n]+' | '+' | '.join(money(b["annual"][y]["net"]) for y in ("2023","2024","2025","2026"))+' | '+money(b["total"]["net"])+' |\n'
    risk='| Book | Worst day | Worst annual closed drawdown | Double-cost total | Without own top five winners |\n|---|---:|---:|---:|---:|\n'
    for n in ("N10","WATCH_FLAT","PREMIUM_LOCK"):
        b=books[n]
        risk+=f'| {labels[n]} | {money(b["total"]["worst_day"])} | {b["total"]["fall_pct"]:.2f}% | {money(b["double_net"])} | {money(b["without_top5"])} |\n'
    accounts='| One continuous Rs 250,000 account | Cost 199 | Cost 200 | Cost 202 | Cost 400 |\n|---|---:|---:|---:|---:|\n'
    for n in ("N10","WATCH_FLAT","PREMIUM_LOCK"):
        accounts+='| '+labels[n]+' | '+' | '.join(money(books[n]["accounts"][str(c)]["end"]) for c in (199,200,202,400))+' |\n'
    check_labels={"annual_net_above_n10":"higher four-year profit", "double_cost_no_worse":"profit under doubled extra costs",
                  "without_own_top5_no_worse":"profit excluding the five best winners", "every_continuous_cost_no_worse":"account value at every tested cost"}
    verdict='\n'.join(f'- **{labels[n]}:** '+('passes ALL frozen economic-superiority checks.' if books[n]["economically_superior"] else 'does NOT pass economic superiority. Failed checks: '+', '.join(check_labels.get(k,k) for k,v in books[n]["superiority_checks"].items() if not v)+'.') for n in ("WATCH_FLAT","PREMIUM_LOCK"))
    detail=f'''# N10.1: improve the mechanics without manufacturing a winning backtest

November 2, 2026. Dev research only. Source freeze `{identity['source_commit'][:7]}`
preceded every score. Controls `{identity['controls_commit'][:7]}` reproduced all
16 prior annuals and 856 economic lifecycles. Production was not edited,
restarted or deployed. No order, Telegram message, capital or live setting changed.

## What was tested

Exactly two hypotheses, specified in [PLAN.md](PLAN.md), on the SAME already
studied 2023–26 years. No feature grid, new entry filter, strategy/member/side
exclusion, threshold tuning or extra size beyond N10's three-lot research cap.

**WATCH_FLAT** corrects N10's excessive floor release: a release requires a flat
account, insufficient free equity for a typical one-lot contract, a selected
contract no more expensive than the median of the last 20 earlier closed shadow
trades, and N10's original 20 newly closed profitable paper outcomes. The 5%
slice and 75% deepest bound remain. A rejected expensive option while holding
another trade is not evidence that the account is permanently stuck.

**PREMIUM_LOCK** also changes the earned third lot. An underlying-price trail
does not guarantee an option price. Before adding, the option's BID must support
a raised premium stop whose net proceeds cover the added lot's 25% premium-stop
loss plus both tranches' fees and extra stress. A refused add changes no stop.
Retry is explicit once per observed minute above+1R; one successful add maximum,
never from 14:45, no re-add after a stopped child. Existing native exits continue.

The 15 earned lots in the original N10 all had cost-aware premium-stop losses greater
than their declared child-risk proxy;12 original combined premium-backstop
exposures exceeded5000. These are alternative planned-risk measurements, not
additional realized losses. An underlying stop may exit sooner; it does not
guarantee the premium. See [diagnosis](n10-risk-diagnosis.json).

## Annual results

Rs 250,000 FRESH each year, normalized 65-unit lots, current fees, archived
candle-derived modeled bid/ask and extra stress. These annual totals are NOT
one compounded account. All amounts below are modeled rupees, never broker P&L.

{table}
{risk}
{verdict}

The strict benchmark was N10 RETRY, not the easier N08 or N09.1 total. Passing
mechanical safety/correctness checks is a separate finding and cannot turn a
failed economic test into success. WATCH_FLAT leaves the inherited retry and
underlying-risk proxy unchanged; only PREMIUM_LOCK repairs the latter.

## Continuous account and cost robustness

No yearly deposit/reset. Carry equity, the floor, decision-observed WATCH peak and consumed
paper evidence across all four years. Cost 199/200/202/400 means the EXTRA cost
function `(base + base/40 * lots)*lots`; modeled spread and current native fees
remain in every arm. The original N10 fine cliff map held its quadratic term
fixed, so these newly declared tests must not be mislabelled as exact replays
of that old map. All three new accounts face the identical cost function.

{accounts}
WATCH paper evidence remains N10's frozen one-lot N08 stream at its original
base stress cost, including in cost-stress arms. Stress changes actual simulated
book cash/reserves/stop funding, not that observer's evidence model. This is a
declared inherited assumption, not a fully re-estimated double-cost shadow.

Lowering the floor spends MORE of the account's lifetime loss budget. It is not
a free recovery or proven predictive edge. The research's 75% bound and three
lots do not change the live 15% halt or one-lot trial. A planned option stop can
gap or fail; all premium remains funded above the floor, and the replay exits
at observed bids, not invented trigger-price fills.

## Attribution and uncertainty

`results.json` records each year's matched-entry delta, changed exits, added
and missed trades, earned-lot contributions, net without the five largest
winners, and 201-week paired comparisons with a 4-week block bootstrap. These
are descriptive uncertainty on seen data, not a new significance test or a
posterior probability of profitability. Read the matched delta alongside the
added/missed net: new admissions can arise from cash/brake feedback rather than
better forecasting. A price-backed stop may protect gains but cut a winning
trade's normal pullback; that opportunity cost stays in the result.

Earned-lot net itself is {money(books['PREMIUM_LOCK']['children']['earned_net'])}
for PREMIUM_LOCK versus {money(books['N10']['children']['earned_net'])} for N10.
The remainder of total net (original positions plus admission/cash feedback)
is {money(books['PREMIUM_LOCK']['total']['net']-books['PREMIUM_LOCK']['children']['earned_net'])}
versus {money(books['N10']['total']['net']-books['N10']['children']['earned_net'])}.
Thus a better-looking add-on contribution can still harm the whole strategy.
Do not tighten the profitable base trade solely to justify another lot. Any
future alternative should preserve base exits and budget added risk honestly,
using actual cash/option-stop exposure rather than guaranteed continuation.

## Verification

80 declared annual executions: 16 controls, 16 candidate annual/cost experiments,
48 continuous year slices. Maximum TWO replay workers. 100 distinct focused tests
pass (27 N10.1/independent validation, 49 N10, 24 native cost/planner/exit/replay).
No full-engine-suite claim. Atlas regenerated: 291 modules, no diff.

Independent checks: `{json.dumps(checks,sort_keys=True)}`.
The audit independently calculates fee arithmetic, reconciles cash including
child closes, checks exact modeled quote prices, own-cash/full-premium reserves,
funded-stop economics, every new premium stop's observed life, strictly earlier
paper evidence/non-reuse and window-keyed terminal state/continuity. Cash-event
drawdowns are retained beside the published combined-trade closed-drawdown basis.
Neither is mark-to-market/open-position drawdown. See [VERIFICATION.md](VERIFICATION.md).

The separate [WATCH peak audit](watch-peak-audit.json) reconstructs actual
closed-cash peaks at every release, including carried history. Every observed
release uses the correct peak and respects its 75% bound. Its saved terminal
`best` can lag a final winning close in {len(peak_audit['terminal_tracker_lags'])}
windows because WATCH updates during planning. The audit retains BOTH that
decision-observed field and the independently calculated actual peak, without
rewriting the frozen policy or its cash. Update tracking on every settlement
before an operational integration; do not advertise a stale terminal field as
an exact high-water mark. No historical release was justified by that lag here.

## Limitations and next action

- Every 2023–26 year was already seen. Even two well-motivated hypotheses may
  still benefit from selection. No claim of an overfit-free profitable strategy.
- 2023 remains a losing year. No known-in-advance day classifier or direction
  edge has been established. Safer position management cannot manufacture one.
- Modeled one-minute quotes are not executable depth; prior clipped requests
  and coverage gaps remain. Lot 65/current fees are normalized research, not
  dated historical broker returns. Stop gaps/slippage/live failures can be worse.
- A Rs 12,500–15,000 one-lot trial cannot inherit this Rs 250,000 reserve policy.
  Do not remove its risk guardrails or allocate more capital from these results.
- Keep the original N10 [2022 exam](../2026-11-01-fno-n10/EXAM_2022.md) unchanged.
  2022 was not acquired, opened or analyzed here. Any new-arm exam needs a
  separately frozen supplement BEFORE reading that data. Its strict driver was
  added after the original round-two source freeze; bind the actual driver too.
- Next useful evidence is a separately frozen forward shadow of N08/N10 and
  the retained correction, with keyed admissions, quote paths, cash/floor and
  actual fee/latency records, fixed review dates/minimum evidence and no broker
  authority. Registering a scheduled task/deploying this code is separate work.

Research wrappers are not a shipping runtime feature. Keep all prior results,
including the failed price-backed hypothesis. No more same-year parameter search
in this round. Primary references: [SOURCES.md](SOURCES.md).
'''
    short=f'''# N10.1: what improved, and what did not

**The account-control correction is built and tested. The price-backed third
lot did not establish an economic improvement over N10 retry.** All four years
were already studied; none of these results proves future profitability.

WATCH_FLAT lowers the floor only when the account is flat and genuinely cannot
fund a typical lot. PREMIUM_LOCK also requires the option's own price to fund
the added lot's protective stop; an underlying trail alone is insufficient.
Stops can still gap. The changes concern recovery, sizing and exits.

Fresh Rs 250,000 EACH year, after modeled costs:

{table}
{risk}
One continuous Rs 250,000 account, no resets/deposits:

{accounts}
{verdict}

The distinction matters: a more accurate risk rule can give up profitable
pullbacks, and a tighter recovery rule can change later admissions. Both costs
are reported. 2023 remains a loss; this did not discover a way to predict every
bad market day or know that an extra lot will win.

**Recommendation:** keep N10 retry as the research profit reference, with its
unproven retry rule clearly labelled. Keep WATCH_FLAT for prospective comparison;
do not promote PREMIUM_LOCK. Its tighter stops gave up too much of the original
positions' earnings. No new live strategy is recommended from this round.

80 annual executions and 100 focused tests; independent cash/fees/prices/stops/
floor/state checks passed. Production and real-money settings unchanged.
Source `{identity['source_commit'][:7]}`; exact controls `{identity['controls_commit'][:7]}`.

Next: prospective keyed shadows and actual execution-cost evidence, or the
separately frozen 2022 exam when the owner acquires it. 2022 was untouched here.
Keep the original N10 exam; do not silently add/tune candidates after reading it.

Full methods, tradeoffs, attribution and uncertainty:
[N10.1 study](research/simulation/2026-11-02-fno-n101/README.md).
'''
    (HERE/"README.md").write_text(detail,encoding="utf-8")
    (DOCS/"FNO_RESEARCH_N101.md").write_text(short,encoding="utf-8")
    (DOCS/"FNO_RESEARCH_N101.json").write_text(json.dumps({"canonical":"N101_WATCH_FLAT","economic_superiority_proven":False,
          "all_years_seen":True,"study":"docs/research/simulation/2026-11-02-fno-n101","identity":identity,
          "results":result,"audit_checks":checks,"deployed":False,"production_untouched":True},indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"report":str(DOCS/"FNO_RESEARCH_N101.md"),"audit_checks":checks}))


if __name__=="__main__":
    main()
