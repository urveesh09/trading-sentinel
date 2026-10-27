"""Populate transparent partial/proxy receipts from existing scored outputs only."""
from collections import Counter
from datetime import date, timedelta
import json
from pathlib import Path

P = Path(__file__).resolve().parent


def main():
    read = lambda name: json.loads((P / name).read_text(encoding='utf-8'))
    results, request, calendar = (read(n) for n in ('results.json', 'request.json', 'calendar.json'))
    coverage = {r['day']: r for r in read('_local/coverage.json')['sessions']}
    sealed = list(read('inputs.json')['files_sha256'])
    arms = [results['control'], *results['candidates']]
    artifacts = ['results.json', 'selection.json', 'summary.json', 'audit.json', 'parity.json',
                 'ANALYSIS.md', 'analyze.py', 'chart.py', 'chart-data.json', 'research-results.png',
                 'research-results.svg', '_local/coverage.json', '_local/search.log']
    limitations = [
        'Every historical session was already seen; neither B nor this search provides untouched validation.',
        'September 18 unavailable; eight recorded sessions have gaps longer than 180 seconds. No interpolation.',
        'Minute-sampled quotes cannot establish executable fills, intragap stop prices, queue position or partial fills.',
        'Closed-trade drawdown excludes intratrade marked losses; all P&L here uses assumed quote-touch execution.',
        'Historical prior closes seed risk; spread closes are exogenous. No unified shared-capital counterfactual.',
        'Exchange calendar cross-checked; contract lot/token identity still archive-derived.',
        'The supplied helper pins pre-freeze Git HEAD; the required freeze commit causes a retained metadata validation failure.',
        'No new strategy qualifies for deployment or consistent-future-profit claims.'
    ]
    for module, arm in zip(request['modules'], arms):
        m = arm['metrics']
        closed = Counter(t['exit_time'][:10] for t in arm['trades'] if 'net_pnl' in t)
        daily = []
        first, last = date.fromisoformat(request['start']), date.fromisoformat(request['end'])
        for offset in range((last - first).days + 1):
            dt = first + timedelta(days=offset); day = dt.isoformat()
            if day in m['daily']:
                reason = 'Recorded-quote portfolio proxy; all execution is assumed, not actual fills.'
                c = coverage[day]
                if c['gaps_over_180_seconds']:
                    reason += f" {c['gaps_over_180_seconds']} gaps >180s; max {c['max_gap_seconds']:.1f}s; archive ends {c['last']}."
                if day in calendar['nifty_expiries_in_window']:
                    reason += ' Verified expiry; inherited entry guard applies.'
                metrics = {'closed_trades': closed[day], 'signals': None, 'filled_fee_pnl': 0,
                           'assumed_pnl': m['daily'][day], 'modeled_net': m['daily'][day], 'unresolved': 0}
                daily.append({'date': day, 'status': 'PARTIAL', 'reason': reason, 'metrics': metrics})
            else:
                nontrading = dt.weekday() >= 5 or day in calendar['holidays_in_window']
                assert nontrading or day in calendar['missing_expected_archive_sessions'], day
                reason = ('Exchange weekend/dated NSE holiday calendar; no trading session.' if nontrading else
                          'Expected exchange session missing from archive; P&L is unknown, never zero.')
                daily.append({'date': day, 'status': 'NOT_APPLICABLE' if nontrading else 'UNAVAILABLE',
                              'reason': reason, 'metrics': {k: None for k in
                              ('closed_trades', 'signals', 'filled_fee_pnl', 'assumed_pnl', 'modeled_net', 'unresolved')}})
        assert abs(sum(x['metrics']['modeled_net'] or 0 for x in daily) - m['net']) < .011
        assert sum(x['metrics']['closed_trades'] or 0 for x in daily) == m['trades']
        row = {'module': module, 'start': request['start'], 'end': request['end'],
               'status': 'PARTIAL', 'fidelity': 'PORTFOLIO_PROXY',
               'population': 'PRIMARY' if module == request['modules'][0] else 'SHADOW',
               'coverage': 'PARTIAL',
               'reason': 'Completed frozen research; incomplete archive and assumed execution prevent a faithful whole-system replay.',
               'metrics': {'closed_trades': m['trades'], 'signals': len(arm['decisions']),
                           'filled_fee_pnl': 0, 'assumed_pnl': m['net'], 'modeled_net': m['net'],
                           'unresolved': m['unresolved'], 'charges': m['charges'],
                           'closed_trade_drawdown': m['drawdown_closed_trades']},
               'inputs': sealed, 'artifacts': artifacts,
               'assumptions': ['Inherited ask entry / bid-else-LTP exit for exact control parity; separate strict bid/depth diagnostic.',
                               'Whole-lot planner, modeled charges, closed-bar 90-second entry clocks and sampled management.',
                               'Filled_fee_pnl=0 means no verified actual executions; every quoted-price result is in assumed_pnl.'],
               'limitations': limitations, 'daily_results': daily}
        (P / 'modules' / (module + '.json')).write_text(json.dumps(row, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print('Three partial/proxy receipts; all 47 calendar dates accounted for and recorded-day cash reconciled.')


if __name__ == '__main__':
    main()
