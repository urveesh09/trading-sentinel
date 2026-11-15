"""SN231-SN250 shared: Gold v6's ledger (SN Gold v5 Rs 30k growing day nets + WK-H's 2-lot daily marks) and monthly tools.
Gold v5's day nets come from SN161's p4.gold (SN110's day player, v5 parity proven); WK-H from SN221's wk3 (the frozen pick)."""
from __future__ import annotations

import datetime as _dt
import pickle
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-15-sn221"))
import wk3  # noqa: E402

wk = wk3.wk
sys.path.insert(0, str(FNO / "2026-11-13-sn161"))
LOCAL = HERE / "_local"
LO, HI = "2023-01-02", "2026-10-29"
WKH = ("STRADDLE", "M", "settle", "H15x2", "none")
WK_SAMPLES = ("DEV", "TEST", "N2122", "SENSEX", "EXAM")


def _cache(name, build):
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / f"{name}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    x = build()
    p.write_bytes(pickle.dumps(x))
    return x


def sessions():
    D = wk.dev_data()
    return sorted(d for d in D["idx"] if LO <= d < HI)


def gold():
    """{day: Gold v5 net} for every day Jan 2023 - Oct 2026 (development + TEST), Rs 30k growing (production)."""
    def build():
        import p4
        return p4.gold("Rs 30k growing (production)", keep=lambda d: True)
    return _cache("gold-v5-days", build)


def daily(t):
    out, prev = {}, 0.0
    for d in sorted(t["marks"]):
        if d > t["exit_day"]:
            break
        out[d] = t["marks"][d] - prev
        prev = t["marks"][d]
    return out


def leg_days(trades, lo=LO, hi=HI):
    ch = {}
    for t in trades:
        for d, x in daily(t).items():
            if lo <= d < hi:
                ch[d] = ch.get(d, 0.0) + x
    return ch


def sample(n):
    if n == "EXAM":
        wk3.UNSEAL_EXAM = True          # seen since SN228
    return wk3.sample(n)


def wkh_trades(n, v=WKH):
    return wk3.book3(sample(n), *v)


def wkh_days():
    """{day: WK-H 2-lot daily mark change} on DEV + TEST (the account window)."""
    def build():
        return leg_days(wkh_trades("DEV") + wkh_trades("TEST"))
    return _cache("wkh-days", build)


def month_of(d):
    return d[:7]


def months(x_by_day, days):
    mo = {}
    for d in days:
        mo[month_of(d)] = mo.get(month_of(d), 0.0) + x_by_day.get(d, 0.0)
    return mo


def refill_months(x_by_day, days):
    """Per month: banked (sum of winning days), refilled (sum of losing days), net."""
    out = {}
    for d in days:
        m = month_of(d)
        r = out.setdefault(m, {"banked": 0.0, "refilled": 0.0, "net": 0.0, "red_days": 0, "green_days": 0})
        x = x_by_day.get(d, 0.0)
        r["net"] += x
        if x > 0:
            r["banked"] += x
            r["green_days"] += 1
        elif x < 0:
            r["refilled"] += -x
            r["red_days"] += 1
    return out


def account_stats(x_by_day, days):
    x = np.array([x_by_day.get(d, 0.0) for d in days])
    mo = months(x_by_day, days)
    v = np.array(list(mo.values()))
    wk_ = {}
    for d, y in zip(days, x):
        iso = _dt.date.fromisoformat(d).isocalendar()
        wk_[(iso[0], iso[1])] = wk_.get((iso[0], iso[1]), 0.0) + y
    return {"net": round(float(x.sum())), "months": len(v), "months_positive": int((v > 0).sum()),
            "worst_month": round(float(v.min())), "second_worst_month": round(float(np.sort(v)[1])) if len(v) > 1 else None,
            "mean_month": round(float(v.mean())), "sd_month": round(float(v.std(ddof=1))) if len(v) > 1 else 0,
            "green_days": int((x > 0).sum()), "red_days": int((x < 0).sum()),
            "worst_day": round(float(x.min())), "worst_week": round(min(wk_.values())),
            "weeks_positive": f"{sum(v_ > 0 for v_ in wk_.values())} of {len(wk_)}",
            "by_year": {y: round(float(sum(x_by_day.get(d, 0.0) for d in days if d[:4] == y))) for y in ("2023", "2024", "2025", "2026")}}


def wk_month_stats(trades, lots=2):
    """A WK-type leg on one sample: per settlement month, per option lot."""
    mo = {}
    for t in trades:
        mo[t["exit_day"][:7]] = mo.get(t["exit_day"][:7], 0.0) + t["net"] / lots
    v = np.array(list(mo.values())) if mo else np.zeros(0)
    return {"net": round(float(v.sum())), "months": len(v), "months_positive": int((v > 0).sum()),
            "worst_month": round(float(v.min())) if len(v) else 0}
