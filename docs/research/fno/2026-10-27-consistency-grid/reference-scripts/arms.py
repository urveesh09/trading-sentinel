"""Exploration on SEEN sessions: quick-trade entry x exit designs, one position at a time, 1 lot, ask in / bid out,
real charges. Development only."""
import json
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

sys.path.insert(0, r"C:\Users\Urveesh\Desktop\trading-sentinel\python-engine")
sys.path.insert(0, __import__("os").path.dirname(__file__))
import explore_lib as L  # noqa: E402

START, END, OUT = (sys.argv[1], sys.argv[2], sys.argv[3]) if __name__ == "__main__" else (None, None, None)


def sig_momo(bars, i):
    b = bars.iloc[i]
    prior = bars.iloc[:i]
    if len(prior) < 3 or not (b["atr"] > 0):
        return None
    rng = b["high"] - b["low"]
    if rng <= 0:
        return None
    if b["close"] > prior["high"].max() and b["close"] > b["vwap"] and (b["close"] - b["open"]) >= 0.5 * rng:
        return "LONG", float(b["low"])
    if b["close"] < prior["low"].min() and b["close"] < b["vwap"] and (b["open"] - b["close"]) >= 0.5 * rng:
        return "SHORT", float(b["high"])
    return None


def sig_pullback(bars, i):
    if i < 7:
        return None
    b, p = bars.iloc[i], bars.iloc[i - 1]
    trend = bars.iloc[i - 6:i]
    a = b["atr"]
    if not (a > 0):
        return None
    if (trend["close"] > trend["vwap"]).all() and b["low"] <= b["vwap"] + 0.25 * a and b["close"] > b["open"] \
            and b["close"] > p["high"] and b["close"] > b["vwap"]:
        return "LONG", float(b["low"])
    if (trend["close"] < trend["vwap"]).all() and b["high"] >= b["vwap"] - 0.25 * a and b["close"] < b["open"] \
            and b["close"] < p["low"] and b["close"] < b["vwap"]:
        return "SHORT", float(b["high"])
    return None


def sig_fade(bars, i):
    if i < 4:
        return None
    b, p = bars.iloc[i], bars.iloc[i - 1]
    before = bars.iloc[:i - 1]
    if p["high"] > before["high"].max() and b["close"] < p["low"] and b["close"] < b["open"]:
        return "SHORT", float(max(p["high"], b["high"]))
    if p["low"] < before["low"].min() and b["close"] > p["high"] and b["close"] > b["open"]:
        return "LONG", float(min(p["low"], b["low"]))
    return None


SIGNALS = {"MOMO": sig_momo, "PULLBACK": sig_pullback, "FADE": sig_fade}
EXITS = {
    # name: (net target, net stop, minutes, underlying atr target, underlying atr stop, use bar stop)
    "X1_200_300_15": dict(tgt=200, stp=-300, mins=15),
    "X2_ATR06_20": dict(utgt=0.6, ustp=0.6, mins=20),
    "X3_200_BARSTOP_20": dict(tgt=200, barstop=True, mins=20),
    "X4_400_400_30": dict(tgt=400, stp=-400, mins=30),
}


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
        busy_until = None
        count = 0
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
            direction, bar_stop = s
            p = L.pick(obs[j], today, direction)
            if p is None:
                continue
            q, delta = p
            qty, entry, fut0 = q.contract.lot_size, q.ask, obs[j].future.ltp
            atr = float(bars.iloc[i]["atr"])
            sign = 1 if direction == "LONG" else -1
            result = None
            for o in obs[j + 1:]:
                cq = o.options.get(q.contract.token)
                hard = o.at.hour * 60 + o.at.minute >= L.settings.FNO_HARD_FLAT_MIN
                timed = o.at >= obs[j].at + timedelta(minutes=ex["mins"])
                if not cq or cq.bid <= 0:
                    continue
                n = L.net(entry, cq.bid, qty)
                move = (o.future.ltp - fut0) * sign
                why = None
                if "tgt" in ex and n >= ex["tgt"]:
                    why = "target"
                elif "utgt" in ex and move >= ex["utgt"] * atr:
                    why = "target"
                elif "stp" in ex and n <= ex["stp"]:
                    why = "stop"
                elif "ustp" in ex and move <= -ex["ustp"] * atr:
                    why = "stop"
                elif ex.get("barstop") and (o.future.ltp - bar_stop) * sign <= 0:
                    why = "stop"
                elif timed or hard:
                    why = "time"
                if why:
                    result = dict(day=day, at=obs[j].at.isoformat(), out=o.at.isoformat(), dir=direction,
                                  sym=q.contract.tradingsymbol, entry=entry, exit=cq.bid, net=round(n, 2), why=why)
                    busy_until = o.at
                    break
            if result:
                trades.append(result)
                count += 1
    return trades


def summary(trades):
    nets = [t["net"] for t in trades]
    days = defaultdict(float)
    for t in trades:
        days[t["day"]] += t["net"]
    run_, peak, dd = 0.0, 0.0, 0.0
    for t in trades:
        run_ += t["net"]
        peak, dd = max(peak, run_), max(dd, peak - run_)
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    return dict(trades=len(nets), net=round(sum(nets)), win_pct=round(100 * len(wins) / len(nets)) if nets else None,
                avg_win=round(sum(wins) / len(wins)) if wins else 0, avg_loss=round(sum(losses) / len(losses)) if losses else 0,
                pf=round(sum(wins) / -sum(losses), 2) if losses and sum(losses) < 0 else None,
                max_dd=round(dd), green_days=sum(v > 0 for v in days.values()), days=len(days),
                why=dict(Counter(t["why"] for t in trades)))


if __name__ == "__main__":
    results = {}
    for s in SIGNALS:
        for x in EXITS:
            tr = run(s, x)
            results[f"{s}/{x}"] = {"summary": summary(tr), "trades": tr}
            print(f"{s:9} {x:18} {summary(tr)}", flush=True)
    json.dump(results, open(OUT, "w"), indent=1, default=str)
