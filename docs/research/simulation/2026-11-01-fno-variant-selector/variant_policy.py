"""N06 research policy: strictly earlier closed labels, unchanged size budgets."""
from collections import defaultdict
from datetime import date, timedelta
import math
import statistics

ORDER = ('BASE', 'STALL30', 'STRUCT30', 'MAIN')


def week(day):
    d = date.fromisoformat(day)
    return (d - timedelta(days=d.weekday())).isoformat()


def drawdown(rows):
    cash = peak = 250000.
    worst = 0.
    for r in sorted(rows, key=lambda r: (r['exit_time'], r['entry_time'])):
        cash += r['net_pnl']
        peak = max(peak, cash)
        worst = max(worst, (peak - cash) / peak)
    return worst


def evidence(records, asof, sessions, anchor):
    if anchor not in ORDER or set(records) != set(ORDER):
        raise ValueError('unknown or incomplete policy inventory')
    date.fromisoformat(asof)
    days = sorted({d for d in sessions if d[:4] == asof[:4] and d < asof})[-84:]
    inside = set(days)
    histories, daily = {}, {}
    for p, rows in records.items():
        histories[p] = [r for r in rows if r['exit_time'][:10] in inside]
        daily[p] = defaultdict(float)
        for r in histories[p]:
            if r['entry_time'] > r['exit_time'] or not math.isfinite(r['net_pnl']):
                raise ValueError('invalid closed label')
            daily[p][r['exit_time'][:10]] += r['net_pnl']
    base = histories[anchor]
    base_dd = drawdown(base)
    weeks = sorted({week(d) for d in days})
    out = {}
    for p in ORDER:
        if p == anchor:
            continue
        diff = {d: daily[p][d] - daily[anchor][d] for d in days}
        weekly = {w: 0. for w in weeks}
        for d, n in diff.items():
            weekly[week(d)] += n
        values = list(weekly.values())
        n = len(values)
        score = statistics.fmean(values) - statistics.stdev(values) / math.sqrt(n) if n >= 2 else None
        without = math.fsum(diff.values()) - max([0., *diff.values()])
        active = sum(abs(v) > 1e-8 for v in diff.values())
        dd = drawdown(histories[p])
        checks = dict(weeks=n >= 8, paired_days=active >= 10,
                      challenger_trades=len(histories[p]) >= 12, anchor_trades=len(base) >= 6,
                      score=score is not None and math.isfinite(score) and score > 0,
                      without_best=without > 0, drawdown=dd <= base_dd)
        out[p] = dict(score=score, eligible=all(checks.values()), checks=checks,
                      paired_days=active, trades=len(histories[p]), anchor_trades=len(base),
                      paired_net=math.fsum(diff.values()), without_best_day=without,
                      drawdown=dd, anchor_drawdown=base_dd)
    return dict(asof=asof, anchor=anchor, window_start=days[0] if days else None,
                window_end=days[-1] if days else None, sessions=len(days),
                latest_label_exit=max((r['exit_time'] for rs in histories.values() for r in rs), default=None),
                profiles=out)


def choose(models, anchor):
    out, pending, count, year = {}, None, 0, None
    for day, m in sorted(models.items()):
        if day[:4] != year:
            pending, count, year = None, 0, day[:4]
        if m['asof'] != day or m['anchor'] != anchor or (m['latest_label_exit'] and m['latest_label_exit'][:10] >= day):
            raise ValueError('noncausal model')
        candidates = [p for p in ORDER if p != anchor and m['profiles'][p]['eligible']]
        candidates.sort(key=lambda p: (-m['profiles'][p]['score'], ORDER.index(p)))
        best = candidates[0] if candidates else anchor
        if best == anchor:
            pending, count, selected = None, 0, anchor
        else:
            count = count + 1 if pending == best else 1
            pending = best
            selected = best if count >= 2 else anchor
        out[day] = dict(variant=selected, best_evidence=best, consecutive_days=count,
                        asof=day, window_start=m['window_start'], window_end=m['window_end'],
                        latest_label_exit=m['latest_label_exit'])
    return out
