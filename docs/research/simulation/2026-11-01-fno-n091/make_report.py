"""Render the completed evidence in plain language; never influences replay decisions."""
from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())


def money(v):
    return ("−" if v < 0 else "+") + "₹" + f"{abs(v):,.0f}"


def polish(text):
    text = re.sub(r"(?m)^-(?=\d)", "- ", text)
    for before, after in {
        "November1,2026": "November 1, 2026", "in2023": "in 2023",
        "Its2025": "Its 2025", "in2025": "in 2025", "all24": "all 24",
        "plus24": "plus 24", "reruns,12": "reruns, 12", "lifecycles,55": "lifecycles, 55",
        "at₹250000": "at ₹2,50,000", "At₹15000": "At ₹15,000",
        "only₹2250": "only ₹2,250", "leaves₹2250": "leaves ₹2,250",
        "this85%": "this 85%", "an85%": "an 85%", "lot65": "lot of 65",
        "2026 endsOct28": "2026 ends October 28", "book at\n": "book at\n",
        "N08's4.70": "N08's 4.70", "fall4.85": "fall 4.85",
        "is4.85": "is 4.85", "source4245670": "source 4245670",
        "Fresh₹250000": "Fresh ₹2,50,000", "start at₹250000": "start at ₹2,50,000",
    }.items():
        text = text.replace(before, after)
    return text


def main():
    identity = json.loads((HERE / "IDENTITY.json").read_text()) if (HERE / "IDENTITY.json").exists() else {}
    r = json.loads((HERE / "results.json").read_text())
    audit = json.loads((HERE / "audit-results.json").read_text())
    stress = json.loads((HERE / "stress-results.json").read_text())
    price = [json.loads((HERE / f"price-audit-{y}.json").read_text()) for y in ("2023", "2024", "2025", "2026")]
    source = "424567044c0d6a3995020835cb3b0a6d2ecaa8fa"
    repair = [json.loads((HERE / f"state-repair-parity-{y}.json").read_text()) for y in ("2023", "2024", "2025", "2026")]
    assert sum(len(rows) for rows in repair) == 24
    assert all(r["exact_economic_parity"] for rows in repair for r in rows.values())
    rows = []
    for name in ("N08", "S_VOL", "VOL_CLOCK", "CUSHION"):
        a = r["aggregates"][name]
        rows.append("| " + name + " | " + " | ".join(money(r["fresh"][name][y]["net"]) for y in ("2023", "2024", "2025", "2026"))
                    + f" | {money(a['net'])} | {a['worst_annual_closed_drawdown_pct']:.2f}% | {money(a['worst_day'])} |")
    accounting = []
    for name, result in r["continuous"].items():
        s = result["summary"]
        accounting.append(f"| {name} | ₹{s['end']:,.0f} | {s['closed_drawdown_pct']:.2f}% | {s['trades']} | "
                          + " / ".join(money(result["by_year"][y]) for y in ("2023", "2024", "2025", "2026")) + " |")
    verdict = []
    for name, v in r["verdicts"].items():
        failed = [key for key, ok in v["risk_checks"].items() if not ok]
        verdict.append(f"- **{name}:** risk route {'PASS' if v['risk_route_pass'] else 'FAIL'}"
                       + (f" (failed: {', '.join(failed)})" if failed else "")
                       + f"; profit route {'PASS' if v['profit_route_pass'] else 'FAIL'}. This is an all-seen development screen.")
    opportunity = []
    for name in ("VOL_CLOCK", "CUSHION"):
        for y, v in r["opportunity_cost"][name].items():
            opportunity.append(f"| {name} {y} | {v['matched']} | {v['resized']} | {money(v['matched_delta'])} | "
                               f"{v['missed_winners']} / {money(v['missed_winners_net'])} | {v['avoided_losers']} / {money(v['avoided_losers_net'])} | "
                               f"{v['added_winners']} / {v['added_losers']} | {money(v['total_delta'])} |")
    stat = []
    for name, s in r["weekly_uncertainty"].items():
        lo, hi = s["four_week_block_bootstrap_95pct_total_delta"]
        stat.append(f"- {name}: paired weekly t {s['paired_t']:.3f}; 4-week block bootstrap total-delta interval {money(lo)} to {money(hi)}. "
                    "Descriptive, all-seen; not a new significance/qualification pass.")
    costs = []
    for name, variants in r["costs"].items():
        costs.append(f"| {name} | {money(sum(s['net'] for s in variants['none'].values()))} | "
                     f"{money(sum(s['net'] for s in variants['double'].values()))} |")
    paths = []
    for name, s in stress["rules"].items():
        paths.append(f"| {name} | ₹{s['worst_end']:,.0f} | ₹{s['lowest_equity']:,.0f} | ₹{s['median_end']:,.0f} |")
    carry = r["continuous"]["CUSHION"]["summary"]
    a, b = r["aggregates"]["CUSHION"], r["aggregates"]["N08"]
    retained = a["net"] / b["net"] * 100
    reduced = (1 - abs(a["worst_day"]) / abs(b["worst_day"])) * 100
    text = f"""# N09.1: budget the exposure, preserve N08's clocks

November 1, 2026. Dev research only. No application, environment, broker, orders,
Telegram, capital authority, restart, deployment or Production change.

**CUSHION retains {retained:.1f}% of N08's modeled aggregate annual profit, with a
{reduced:.1f}% smaller worst day.** It ends the no-reset continuous account at
₹{carry['end']:,.0f}. Read the frozen verdict below before treating this as a lead.
This is a loss-control hypothesis, not a new direction predictor. It does not
turn 2023 profitable, and all four years were already seen.

## The two concrete N09 issues

1. **Sizing comparison changed two things.** N09 S_VOL sets low_two_lots_before
   to1440, whereas N08 uses720. It both applies volatility sizing and expands
   the time window where a second lot can be considered. This is a research
   design confound, not a discovered live-order bug. VOL_CLOCK preserves all
   N08 clocks and only reduces size. Do not describe S_VOL as a pointwise size
   reduction of N08 on identical state.
2. **The whole-year SHADOW stress diagnostic used the current outcome.** In
   N09 stress_years.path_end, paper.append(net) precedes the restart decision
   and that same net can be booked. The corrected event proxy only permits
   labels whose exit is strictly before the new entry. A synthetic regression
   demonstrates the difference. The original results remain unchanged. This
   finding does not invalidate the separate full N09 account replays, which
   use prior timestamps correctly.

## What N09.1 changes

- VOL_CLOCK: N08 plus N09's prior-day ATR-versus-prior250-session median sizing,
  only allowed to reduce the native count. The before-noon low-day two-lot
  ceiling and14:00 last entry stay intact. Missing volatility means at most1lot.
- CUSHION: VOL_CLOCK plus full remaining premium/current fee/stress reservation
  above a floor initially85% of starting equity. The floor ratchets with closed
  high-water equity only when already-open exposure can fund it; it never falls.
  Choose the largest whole lot count accepted by the native planner that fits.
  Recompute a smaller native plan before creating the position. If even1lot
  cannot fit, decline the admission; continue every existing exit.
- Both: N08 signals, member priority, exits, expiry rules, own-cash restrictions,
  original risk budgets and hard deadlines remain. At most2lots. No averaging
  down, new option selling, margin, new capital or automatic halt reset.

The reserve explicitly allows the option to lose its entire premium; it does
not assume an SL fills at its requested price. The historical model still lacks
actual depth, broker fills and operational failures, so this is no live guarantee.

**Capital scope matters:** these accounts start at₹250000. At₹15000 an85%
floor initially leaves only₹2250 for full premium plus fees/stress. A whole
eligible lot can exceed that amount, so applying CUSHION unchanged could reject
most or all entries. It is not a drop-in change for the small live trial and
does not justify increasing capital or relaxing its approved risk limits.

## Fresh annual accounts

Fresh₹250000 each year; lot65 throughout;2026 endsOct28. Current fee model,
modeled adverse bid/ask and extra stress(200+5×lots)×lots are inside each cash path.
The sum is a comparison of separate experiments, not one investor's return.

| Book | 2023 | 2024 | 2025 | 2026 | Sum | Worst annual closed fall | Worst day |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## One account, no fresh annual capital or loss-budget reset

The original 15% initial-capital halt remains for every book; CUSHION adds a
stricter funded admission budget. Closed cash/risk history and CUSHION state
carry through year boundaries. This is a full candle-book replay with
its own admissions, not a sum of annual accounts or fixed-trade scaling.

| Book | Ending equity | Closed fall | Trades | Year contributions2023/24/25/26 |
|---|---:|---:|---:|---|
{chr(10).join(accounting)}

## Frozen verdict; no moved goalposts

{chr(10).join(verdict)}

Risk route: retain>=90% aggregate profit; worst day>=20% smaller; worst annual
closed fall no larger;2024-26 positive; continuous end>=never-restartedN08;
double-extra-cost aggregate positive. Profit route separately requires more
aggregate profit/no worse worst day/worst annual fall/2023/no worse continuous
end/positive double cost. No result qualifies a strategy for deployment.

**Opportunity cost:** CUSHION sacrifices ₹{b['net']-a['net']:,.0f} of aggregate
annual profit. Its2025 closed fall is{r['fresh']['CUSHION']['2025']['closed_drawdown_pct']:.2f}%
versus N08's{r['fresh']['N08']['2025']['closed_drawdown_pct']:.2f}%: it does not
dominate N08 on every year's risk. The risk criterion concerns the worst annual
fall, as predeclared. All per-year returns and costs remain visible.

## Where the difference comes from

Exact match requires entry timestamp, contract, signal bar, original stop and
target. Changed quantity is shown separately from removed/added opportunities.
New/missed trades can follow changed cash and native brakes; these are not
proof of new predictive signals. Each row's components reconcile to its delta.

| Book/year | Matched | Resized | Matched delta | Missed winners/count net | Avoided losses/count net | Added wins/losses | Total delta |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(opportunity)}

## Costs and uncertainty

These are separate complete replays: zero/double refers only to EXTRA stress.
Current charges and modeled adverse quotes remain; none measures actual costs.

| Book | Zero extra stress, annual net sum | Double extra stress, annual net sum |
|---|---:|---:|
{chr(10).join(costs)}

{chr(10).join(stat)}

## Repeated bad-year diagnostic

All256 ordered four-year sequences with replacement, fixed1lot N08 no-brake
admission universe. Entry/exit clocks are preserved; still a PORTFOLIO_PROXY:
no regenerated market decisions, risk-sized lots or complete native brakes.
CUSHION here is the floor component at1lot; VOL_CLOCK cannot change1lot size.
Do not compare these rupee levels to the full continuous replays above or infer
probabilities of future ruin from256 reused historical sequences.

| Rule | Worst ending equity | Lowest equity | Median ending equity |
|---|---:|---:|---:|
{chr(10).join(paths)}

CorrectedSHADOW helps{stress['versus_none']['SHADOW']['helps']},
hurts{stress['versus_none']['SHADOW']['hurts']}, is unchanged on
{stress['versus_none']['SHADOW']['same']} versusNONE. CUSHION also sacrifices
strong paths: hurts{stress['versus_none']['CUSHION']['hurts']} of256. Its
maximum opportunity cost is{money(stress['versus_none']['CUSHION']['largest_cost'])}.
Protecting capital has a real price; no selective reporting of the weak years.

## Verification and limitations

- Pre-score source{source[:7]}, exact-control/stress reportingc5351a7.
  Frozen2hypotheses;60 completed annual books;12 exact controls/675 old trades.
  An audit caught fresh terminal states keyed only by policy; later independent
  years overwrote earlier terminal snapshots. Original per-trade/admission
  evidence and unique continuous state survived. Post-score correctionc6bbcb9
  and freeze-v2 are disclosed in SOURCE_CORRECTION.md/json. All actual trading
  function ASTs/config/rules/acceptance stayed unchanged.24 fresh-namespace
  replays exactly reproduce old economic trades AND complete decision/admission
  receipts and retain every full-window terminal state.84 executions total,
  not84 independent experiments; the original60 remain the scored experiment.
-55 focused checks:21 N09.1,23 N09,11 native exit/replay. No full-suite claim.
- A subsequent checker-only comparison used sub-paise tolerance against the
  native two-decimal opening display. CHECKER_CORRECTION.md documents the
  0.0029-rupee example and one-paise display comparison; economics unchanged.
- Independent audit:{json.dumps(audit['counts'], sort_keys=True)}.
  Price checks:{sum(p['prices_checked'] for p in price)} modeled entry/exit prices.
-945 source and972 cached-input/old-receipt hashes bound before scoring.
  Frozen cached candles are reused; no fresh broker data/2022/download calls.
- Normalized65-unit lots/current fees are NOT dated historical broker returns.
  Original clipped candles and known gaps remain; at least one old N08 trade
  touched a clipped session. No IV/depth/Greeks explanation is invented.
- Drawdowns are CLOSED-equity drawdowns. No claim about worst intratrade marks,
  future loss limits or guaranteed trade execution. No out-of-sample claim.
- N08/N09/checkpoints/application source preserved. Production stays unchanged.

## Next

Retain N08 as the aggregate-profit reference. Treat any passing N09.1 risk screen
as a candidate for prospective evidence, not a replacement proved to make money.
Freeze and build keyed broker-free forward shadows, recording every budget
decision, missed winner, costs, cash and floor. Test actual charges/fills only
when authorized observations exist. Keep2022 unopened until a complete test
rule and coverage contract are fixed. No automatic live floor reset or lot rise.

Reproduction/commands: VERIFICATION.md. Detailed machine evidence: results.json,
audit-results.json, control-parity.json, price-audit-*.json and stress-results.json.
Mechanism references and limits: SOURCES.md. OriginalPLAN and freeze preserved.
"""
    if identity:
        text += "\nResults and independent audit: `" + identity["results_and_independent_audit"][:7] + "`, pushed. Full identities: IDENTITY.json.\n"
    (HERE / "README.md").write_text(polish(text), encoding="utf-8")
    root = f"""# N09.1: exposure control beside N08

November1,2026. Dev research only; Production unchanged.

CUSHION retains {retained:.1f}% of N08's modeled annual aggregate profit, reduces
the worst day by {reduced:.1f}%, and ends a continuous account without resets at
₹{carry['end']:,.0f}. It remains losing in2023 and gives up ₹{b['net']-a['net']:,.0f}
of aggregate annual profit. All four years are already seen; no proven new edge.

| Book | 2023 | 2024 | 2025 | 2026 | Sum | Worst annual closed fall | Worst day |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

{chr(10).join(verdict)}

N09.1 preserves N08's before-noon/14:00 rules, applies the existing prior-day
volatility rule only to reduce size, and CUSHION reserves full long premium,
fees and declared stress above a cash-backed nondecreasing floor. Entry and exit
signal rules stay unchanged. No option selling, margin, risk expansion, halt
reset or money authority is introduced.

N09's S_VOL also expanded its second-lot time window; N09.1 isolates this.
The separate N09 repeated-year SHADOW diagnostic used the same outcome to
justify and book a restart trade. Corrected strictly-prior entry/exit stress
still shows substantial repeated-loss risk. Original N09 full timestamped
account replays are a separate scope and remain intact.

2025's CUSHION fall{r['fresh']['CUSHION']['2025']['closed_drawdown_pct']:.2f}% is
slightly worse than N08's{r['fresh']['N08']['2025']['closed_drawdown_pct']:.2f}%;
it is not better on every metric. Keep N08 as the profit reference and use new
forward shadow evidence to assess any N09.1 risk lead before deployment.

Capital scope: tested at₹250000. At₹15000 this85% floor leaves₹2250 for
the full premium plus costs and can make a whole lot unaffordable. It is not a
drop-in change for the small live trial. No capital increase is recommended.

60 annual experiments plus24 exact state-repair reruns,12 exact controls/675 old
lifecycles,55 focused checks,
independent financial/admission/state/floor checks and
{sum(p['prices_checked'] for p in price)} modeled-price checks. Partial candle
fidelity, normalized lots/current costs, assumed extra stress; no real fills.

Full report: [N09.1 study](research/simulation/2026-11-01-fno-n091/README.md).
An independent audit caught overwritten fresh-year terminal snapshots. The
post-score correction preserves original scores and exactly matches all24
affected trade/decision receipts on rerun. Full account state is independently
audited; details are in the study's SOURCE_CORRECTION.md.
Pre-score source4245670. Results commit identity is recorded in the successor
handoff after commit. No application/env/migration/Production changes.
"""
    if identity:
        root = root.replace("Results commit identity is recorded in the successor\nhandoff after commit.", "Results and independent audit: " + identity["results_and_independent_audit"][:7] + ", pushed; see the study's IDENTITY.json.")
    (ROOT / "docs/FNO_RESEARCH_N091.md").write_text(polish(root), encoding="utf-8")
    checkpoint = {"schema": "n091_checkpoint_v1", "source_commit": source, "all_data_seen": True,
        "status": "research_only_not_deployed", "reference": "N08", "candidates": r["verdicts"],
        "canonical_risk_candidate": "N091_CUSHION_VOL_CLOCK", "canonical_primary_book": "CUSHION",
        "artifact_correction_commit": "c6bbcb969bed7389989e53e1ed3e77bb9bcd451b",
        "book_keys": {p: {y: json.loads((HERE / f'_local/keys-{p}-{y}.json').read_text()) for y in ('2023','2024','2025','2026')} for p in ('controls','primary','costs','carry')},
        "fresh": r["aggregates"], "continuous": {n: s['summary'] for n,s in r['continuous'].items()},
        "results": (HERE / "results.json").relative_to(ROOT).as_posix(),
        "unchanged_runtime": True, "qualification": "unqualified; all-seen risk screen only"}
    if identity:
        checkpoint["results_commit"] = identity["results_and_independent_audit"]
    (ROOT / "docs/FNO_RESEARCH_N091.json").write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    print("REPORT_WRITTEN", retained, reduced, carry['end'])


if __name__ == "__main__":
    main()
