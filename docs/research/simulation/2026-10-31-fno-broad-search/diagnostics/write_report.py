"""Render the complete, already-scored trial ledger without selecting new rules."""
import json,re
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
load=lambda p:json.loads(p.read_text())
YEARS=('2024','2025','2026')
money=lambda n:f'{n:+,.0f}'
label=lambda n:n.replace('|',' / ')


def run():
    s=load(HERE/'calendar/screen-results-v2.json');c=load(HERE/'calendar/selected-results-v2.json')
    checks=load(HERE/'crosschecks.json');expr=load(HERE/'expression-crosschecks.json')
    rows=['# All48 frozen genomes — complete trial ledger','',
          'Canonical corrected calendar; one lot65, archived options, shipped fees and modeled spread, then extraRs200/trade. Diagnostic brakes disabled. All years seen. These are independent research books, not deployable results or a summed portfolio. Genes jointly vary, so this is not a clean attribution of exit versus stop versus lookback effects.','',
          '| Genome | 2024 net / trades | 2025 net / trades | 2026 net / trades | Three-year sum | Max-t p | Pass |',
          '|---|---:|---:|---:|---:|---:|---|']
    for n,v in sorted(s['candidates'].items()):
        z=v['standalone'];cells=[money(z['years'][y]['net'])+' / '+str(z['years'][y]['trades']) for y in YEARS]
        rows.append('| '+label(n)+' | '+' | '.join(cells)+f" | {money(z['total'])} | {v['max_t_p']} | {v['screen_pass']} |")
    rows+=['','All eight random controls are retained in calendar/screen-results-v2.json; their best three-year result is Rs'+money(s['random_best_valid'])+'. Direction proposals and every acceptance flag are in calendar/selected-results-v2.json. No original unresolved arm was silently dropped: original screen-results.json retains all15, corrected records are separate.']
    (HERE/'TRIAL_LEDGER.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    report=['# Broad F&O gap search — October31,2026','',
        '**Result:** '+('No new addition clears the frozen acceptance bar.' if not c['passing'] else 'Exploratory survivors: '+', '.join(c['passing'])+'; none is freshly qualified.')+' No main-book rule, application, real-money switch or Production service was changed.','',
        'The search is complete:48 fixed genome-style variants across12 entry families; eight deterministic random controls; three main/TPB controls; corrected special-session replays; three direction-restricted proposals and their actual shared-main-book replays. Separately,15 bounded option expressions were compared at two execution-cost levels. This is a broad fixed population, not repeated mutation until an attractive number appears.','',
        '## What the direction-specific proposals actually did','',
        'Only2024+2025 selected these directions. The list was committed as60c27eb before child replays. All three years had been studied previously;2026 is an internal stability check, not a clean holdout. Direction subsetting only proposed candidates; the table below uses actual reruns. Standalone numbers use one normalized lot and extraRs200 per trade. Combined numbers start each year with a freshRs250,000 and apply normal main-book sizing, costs and brakes. Annual profits are not a continuous account balance or a forecast forRs15,000.','',
        '| Book | 2024 | 2025 | 2026 through Oct28 |', '|---|---:|---:|---:|',
        '| Main, shared-book control | '+' | '.join(money(s['controls'][y]['net']) for y in YEARS)+' |']
    for n,v in c['candidates'].items():
        report+=['| '+label(n)+' standalone | '+' | '.join(money(v['standalone']['years'][y]['net']) for y in YEARS)+' |',
                 '| Main + '+label(n)+' | '+' | '.join(money(v['combined'][y]['net']) for y in YEARS)+' |']
    report+=['','| Proposal | Standalone trades by year | Failed predeclared checks | Selected max-t p |', '|---|---|---|---:|']
    for n,v in c['candidates'].items():
        report.append('| '+label(n)+' | '+' / '.join(str(v['standalone']['years'][y]['trades']) for y in YEARS)+' | '+', '.join(k for k,z in v['checks'].items() if not z)+f" | {v['selected_max_t_p']:.3f} |")
    report+=['','Largest annual falls in the closed-trade cash curve: main '+f"{100*max(v['fall_pct'] for v in s['controls'].values()):.2f}%"+'; '+
             '; '.join(label(n)+f" {100*max(y['fall_pct'] for y in v['combined'].values()):.2f}%" for n,v in c['candidates'].items())+
             '. These exclude intratrade marks. The time-of-day addition reached27.96% and fails the drawdown bar; risk brakes are not a guaranteed maximum loss.']
    report+=['','No two-sided parent genome was profitable in all three years. [Full48-genome ledger](TRIAL_LEDGER.md) includes every failed arm; no winner-only presentation. All-eight random results, half-year/sample/best-day checks, costRs300 sensitivity, weekly tests and drawdown comparisons remain in the JSON results.','',
        '## Breadth and what failed','',
        'The12 families were moving-average crossovers, adaptive-average turns, channel breakouts, Bollinger re-entry, CCI re-entry, RSI divergence, regression reversion, failed prior-day levels, gap repair, compression breakout, OBV-confirmed breakout, and momentum from earlier sessions at the same clock. Each had four fixed combinations of horizon10/20 bars, stop1/1.5 ATR, target2/3 risk units, and existing LIVE/RUN exit profiles. New entries used their own logic on dailyADX<30 days; they did not inherit the old four-strategy stretch filter. Main remained ADX30/stretch0.5 with its own exits and brakes.','',
        'For example, channel-breakout g2 earned aboutRs52,663 in2024 but lostRs113,494 in2025 andRs33,711 in2026 after the allowance. RSI-divergence g3 earnedRs27,704 in2026 but lostRs69,637 in2024. These are descriptive examples, not proposed year switches. A good historical year does not tell the system in advance when the rule will work. The shared four-week-block sign-flip sensitivity preserves arm correlation, but cannot correct all previous searches, all proposed subsets, or repeated use of these years.','',
        '## What the loss-making parts have in common','',
        'All222 main/TPB entries were reconstructed from causal inputs. Mutating future minute prices and daily prices unavailable at the signal left every feature unchanged. Partitions by side, member, prior trend, volatility, VWAP location, range, volume, gap and clock reconcile to the control totals. These are diagnostic slices, not backtested new filters.','',
        '| Main component | Trades | Net after extraRs200 | Before that extra allowance |', '|---|---:|---:|---:|',
        '| Calls | 56 | −7,662 | +3,538 |','| EFF | 71 | −13,956 | +244 |','| TPB | 20 | +31,070 | +35,070 |','',
        'The before-allowance column already includes shipped fees and modeled bid/ask. It is not gross profit. EFF still lost in2024/2025 even before the extra allowance, and calls still lost in2024/2026. Costs are material but are not the only explanation. Daily DMI or EMA agreement did not consistently turn the main book profitable in each year. TPB low-ADX puts remain the existing more promising control (+13,199/+27,831/+23,560 one-lot standalone); that is previously seen evidence, not a discovery or qualification from this round.','',
        '## Can an option structure fill the gap?','',
        'Tested:50/100/150-point debit verticals, inverse credits, same-direction credits using the other option type, and neutral ironfly/condors with widths50/100 and offsets0/50/100. Every leg required a positive-volume exact-minute candle at both recorded entry and exit; missing/incoherent quotes remained unavailable. Prices use adverse modeled bid/ask, four/eight-order current fees and extraRs200/Rs400 per complete structure. Entry risk uses entry-only information; full-width/two-width cash is reserved, with no credit-funded exposure.','',
        'No expression clears the frozen95%-risk-compatible-coverage, sample, all-year-positive atRs400, best-day and same-cohort-improvement bar. A150-point debit on main puts looks positive on a tiny compatible subset (+556/+71/+173), but covers only4/16,2/25,5/23 requested trades and underperforms those same single-leg trades. A complete50-point same-direction credit on main calls loses roughlyRs6,708/Rs15,351/Rs7,239 atRs400 extra. Wider or favorable-only subsets are not reliable replacements.','',
        f"All{expr['parent_records']} parent records are sealed by file and record hashes. {expr['original_rows_bound_and_repriced']:,} original expression rows were independently rebound/repriced, plus{expr['extension_bound_rows']:,} extension rows checked for exact economic binding and financial identities. Those6,660 rows reuse222 signals; they are not independent trades. Stored stops are closing/trailing fields, not immutable initial-stop evidence.", '',
        'These are matched-clock expression diagnostics, not a spread portfolio or independently timed volatility strategy. They do not model a joint spread stop, hedge-first order lifecycle, partial leg fills, historical broker margin or aRs15,000 account. No conclusion that every credit/neutral strategy fails follows from this test. A true adapter is required before one can claim such a strategy trades profitably. [Primary-source mechanics and limits](expressions/SOURCES.md), [broader research map](SOURCES.md).','',
        '## Correctness and limits','',
        f"- {checks['fresh_replay_files']} fresh replays, {checks['counts']['closed_records']:,} closed records reconciled; max net discrepancy belowRs0.00005. Original15 unresolved records remain preserved; corrected screen and children have zero unresolved. The many replay records share the same699 sessions and are not independent market evidence.",
        '- Special March2/May18,2024 sessions closed12:30. A separately frozen calendar repair uses entry cutoff12:00/hard flat12:25 only on those dates, with actual observations and no invented break quotes. All59 2024 arms were rerun;118 ordinary2025/26 outputs were reused with exact hashes and inactive-date proof. Main/TPB controls and ordinary raw records match. This clock is a declared research assumption, not a historical live-execution claim.',
        '- All699 cached sessions freshly reparsed from sealed raw candles and identical; original/source/memo/settings/data and nested source hashes checked. No market-data API calls or downloads. Known2025 negative-volume bars, missing depth/gaps, UNKNOWN archived regimes, normalized lot65 and current rather than historical fees remain limitations. No historical fill guarantee.',
        '- 138 focused tests passed; no full-engine-suite claim. Production availability remained HTTP200 at the recorded checks; its checkout stayed c97cb8c3ba0eeb4ac8e9966135b07034d760b40d. No edits/restarts/orders/messages/capital activation.',
        '- Preparatory calendar harness launch failures (wrong cache field and uncommitted regenerated receipt) were caught before any corrected replay. Source was corrected/re-frozen before scoring; logs, failed versions and planned bounded-slice timeouts are retained. [Commands and commit handoff](VERIFICATION.md).','',
        '- Final reporting review caught NumPy boolean checks serialized as text. Original outputs remain intact; v2 files strictly normalize51 known flags, recheck numeric statistical contracts, and preserve every economic metric and rejection verdict. Reports use v2. The11 new regression checks include the actual NumPy/JSON reproducer and reject ambiguous or inconsistent flags. No strategy or threshold changed.','',
        '## Concrete next work','',
        '1. Keep these additions out of runtime. Preserve current main, existing TPB-put and no-EFF comparisons; do not replace them because one new calendar year or subset looked attractive.',
        '2. Run the original2023 exam with its six books unchanged after verified acquisition. Its own rule, candidate list and owner decision remain authoritative. Do not append this round’s proposals to that exam. No2023 test was scored here; earlier daily/futures warmup is not a full untouched option exam.',
        '3. Measure actual entry/exit spreads, quote age, displayed depth and fill slippage by clock/liquidity on prospective observations. Replace the conservative execution allowance only with evidence and a new frozen comparison. Preserve adverse tails; do not lower costs simply to pass.',
        '4. Repair/validate negative-volume and special-session inputs as a separately versioned data/adapter task. Preserve original receipts and compare every affected session. A candidate whose conclusion depends on the special clock needs an independently frozen clock sensitivity before any promotion.',
        '5. Research event/news reaction, constituent-relative strength or volatility selection only after obtaining timestamped arrival/revision histories, point-in-time constituents, or suitable multi-leg quotes. Current unsigned volume/price candles cannot supply signed order flow or historical executable depth.',
        '6. If a funded spread idea later warrants further work, first build a two/four-leg lifecycle with entry-only cash/margin checks, no uncovered leg, partial-fill/recovery behavior, conservative exits and genuine shared-account replay. This round’s paired returns cannot substitute for it. Freeze a small new question and prospective paper acceptance before tuning.',
        '',
        'Research is complete and stored in Dev. Nothing here proves future profitability, permits deployment, changes strategy authority, or guarantees capital preservation. A smarter entry/exit system needs repeatable decision value after costs; this search did not establish that value for a new addition.']
    text='\n'.join(report)+'\n'
    text=text.replace('Rs','₹').replace('October31','October 31').replace('Oct28','Oct 28').replace('dailyADX','daily ADX').replace('stayedc97','stayed c97')
    text=re.sub(r'\b(All|all|The|the|Only|only|No|no|about|before|from|through|and|on|of|than|with|below|corrected|original|complete|those|Known|normalize|reached|across|as|closed|cutoff|flat|frozen|Full|in|March|May|ordinary|Original|plus|reuse|same|Those|HTTP|stretch|ADX)(?=\d)',r'\1 ',text)
    text=re.sub(r'([A-Za-z][,:;])(?=\d)',r'\1 ',text).replace('All-eight','All eight')
    for old,new in [('lot65','lot of 65'),('lot65','lot of 65'),('horizon10/20','horizons of 10/20'),('stop1/1.5','stops of 1/1.5'),('target2/3','targets of 2/3'),('widths50/100','widths of 50/100'),('offsets0/50/100','offsets of 0/50/100'),('retained;118','retained; 118'),('rerun;118','rerun; 118')]:text=text.replace(old,new)
    text=re.sub(r'([a-zA-Z])₹',r'\1 ₹',text)
    (HERE/'README.md').write_text(text,encoding='utf-8')


if __name__=='__main__':run()
