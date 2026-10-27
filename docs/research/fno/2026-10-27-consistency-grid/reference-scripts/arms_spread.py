"""Exploration on SEEN sessions: the quick signals traded as a 100-point debit spread (buy the delta-0.55 strike,
sell 100 points further out), DR-style exits. Plus the cost per single-leg round trip. Development only."""
import json
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

sys.path.insert(0, r"C:\Users\Urveesh\Desktop\trading-sentinel\python-engine")
sys.path.insert(0, __import__("os").path.dirname(__file__))
import explore_lib as L  # noqa: E402
from arms import SIGNALS, summary  # noqa: E402  (arms.py runs its grid on import: guarded below)

START, END, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
WIDTH = 100
EXITS = {
    "DR_HALF_60_SQ": dict(tgt=0.5, stp=0.6, mins=None),
    "DR_HALF_60_60M": dict(tgt=0.5, stp=0.6, mins=60),
    "DR_THIRD_50_30M": dict(tgt=1 / 3, stp=0.5, mins=30),
}


def leg_costs(buy, sell, qty):
    return L.calc_fno_costs(buy, sell, qty)


def run(sig_name, exit_name):
    sig_fn, ex = SIGNALS[sig_name], EXITS[exit_name]
    trades = []
    for day in L.data.days:
        if not (START <= day <= END) or date.fromisoformat(day) in L.calendar:
            continue
        got = L.cached(day)
        if got is None:
            continue
        obs, bars, today = got
        busy_until, count = None, 0
        for i, j in L.closes_with_obs(obs, bars):
            end = bars.index[i] + timedelta(minutes=5)
            minute = end.hour * 60 + end.minute
            if not (L.settings.FNO_ENTRY_START_MIN <= minute < 14 * 60 + 30) or count >= 6:
                continue
            if busy_until is not None and obs[j].at <= busy_until:
                continue
            s = sig_fn(bars, i)
            if s is None:
                continue
            direction = s[0]
            p = L.pick(obs[j], today, direction)
            if p is None:
                continue
            long_q = p[0]
            c = long_q.contract
            far = c.strike + WIDTH if direction == "LONG" else c.strike - WIDTH
            short_q = next((q for q in obs[j].options.values() if q.contract.expiry == c.expiry
                            and q.contract.instrument_type == c.instrument_type and q.contract.strike == far), None)
            if short_q is None or short_q.bid <= 0:
                continue
            qty = c.lot_size
            debit = long_q.ask - short_q.bid
            if debit <= 0 or debit >= WIDTH:
                continue
            max_profit, max_loss = (WIDTH - debit) * qty, debit * qty
            result = None
            for o in obs[j + 1:]:
                lq, sq = o.options.get(c.token), o.options.get(short_q.contract.token)
                hard = o.at.hour * 60 + o.at.minute >= L.settings.FNO_HARD_FLAT_MIN
                timed = ex["mins"] is not None and o.at >= obs[j].at + timedelta(minutes=ex["mins"])
                if not lq or not sq or lq.bid <= 0 or sq.ask <= 0:
                    continue
                value = lq.bid - sq.ask
                gross = (value - debit) * qty
                n = gross - leg_costs(long_q.ask, lq.bid, qty) - leg_costs(sq.ask, short_q.bid, qty)
                why = None
                if gross >= ex["tgt"] * max_profit:
                    why = "target"
                elif gross <= -ex["stp"] * max_loss:
                    why = "stop"
                elif timed or hard:
                    why = "time"
                if why:
                    result = dict(day=day, at=obs[j].at.isoformat(), out=o.at.isoformat(), dir=direction,
                                  sym=c.tradingsymbol, debit=round(debit, 2), net=round(n, 2), why=why)
                    busy_until = o.at
                    break
            if result:
                trades.append(result)
                count += 1
    return trades


results = {}
for s in ("MOMO", "FADE"):
    for x in EXITS:
        tr = run(s, x)
        results[f"{s}/{x}"] = {"summary": summary(tr), "trades": tr}
        print(f"{s:6} {x:16} {summary(tr)}", flush=True)
json.dump(results, open(OUT, "w"), indent=1, default=str)
