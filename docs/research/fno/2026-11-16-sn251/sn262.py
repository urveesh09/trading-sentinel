"""SN262 - a learned move-size model (PLAN.md). LightGBM predicts "the 10:00 ATM straddle held to 15:10 (Rs 3,000
stop) ends positive". Features at 10:00 only: realised / implied since 09:20 (SN95's R_today), the 30-minute opening
range, the gap (signed and absolute), the move since the open, yesterday's range, the last 5 daily returns' spread,
sessions to expiry, the weekday. The VIX ratio is left out (VIX starts in 2021, so EXAM-N's 2020 has none; decided
before any SN262 score). DEV walk-forward by year: each year 2023-2026 is predicted by a model trained on every earlier
DEV day (from Apr 2022); 2022 is training only, so the max-min runs over 2023-2026. Trade when the probability is in
the top 10% / 20% of that model's training predictions. TEST and the exams use one model trained on all DEV, with the
DEV quantile. Null "day": the straddle on as many random sessions. 2 variants."""
from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402
import legs as LG  # noqa: E402
import slot  # noqa: E402

I0 = gl.I["10:00"]
OVERNIGHT_MIN = 125.0
PRED = {}


def r_today(smp, s, i=I0):
    st = smp.mk["step"]
    c = float(s["index"][3][i])
    K = int(round(c / st) * st)
    ce, pe = gl.opx(s, K, "CE", i, 5), gl.opx(s, K, "PE", i, 5)
    if ce is None or pe is None:
        return None
    n = smp.sessions_until(s["day"], s["expiry"])
    tau = (375 - (i + 1)) + 375.0 * n + OVERNIGHT_MIN * n
    si = (ce + pe) / (0.7979 * float(s["future"][3][i]) * math.sqrt(tau))
    cc = np.asarray(s["index"][3][5: i + 1], dtype=np.float64)
    return float(np.std(np.diff(np.log(cc)))) / si if si > 0 else None


def features(smp, d):
    s = smp.s[d]
    ix = s["index"]
    o = float(ix[0][0])
    pb = smp.prev_bar(d)
    bars = [smp.prev_bar(d, k) for k in range(1, 7)]
    rt = r_today(smp, s)
    if pb is None or rt is None or any(b is None for b in bars):
        return None
    rets = np.diff(np.log([b[3] for b in bars[::-1]]))
    return [rt, (float(np.max(ix[1][:30])) - float(np.min(ix[2][:30]))) / o, o / pb[3] - 1.0, abs(o / pb[3] - 1.0),
            float(ix[3][I0]) / o - 1.0, (pb[1] - pb[2]) / pb[3], float(np.std(rets)), smp.sessions_until(d, s["expiry"]),
            dt.date.fromisoformat(d).weekday()]


def target_trade(smp, d, stress=gl.STRESS, late=0):
    return LG.intraday(smp, d, LG.straddle(smp, smp.s[d], I0), I0, gl.FLAT, stress=stress, late=late)


def fit(X, y):
    import lightgbm as lgb
    m = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=8, min_child_samples=30, subsample=0.8,
                           subsample_freq=1, colsample_bytree=0.8, random_state=262, verbose=-1)
    m.fit(np.array(X), np.array(y))
    return m


def build():
    dev = gl.sample("DEV")
    rows = {}
    for d in dev.days:
        f = features(dev, d)
        t = target_trade(dev, d)
        if f is not None and t is not None:
            rows[d] = (f, 1 if t["net"] > 0 else 0)
    for q in (0.10, 0.20):
        PRED.setdefault(q, {"DEV": {}})
        for y in ("2023", "2024", "2025", "2026"):
            tr = [d for d in rows if d < f"{y}-01-01"]
            te = [d for d in rows if d[:4] == y]
            m = fit([rows[d][0] for d in tr], [rows[d][1] for d in tr])
            p_tr = m.predict_proba(np.array([rows[d][0] for d in tr]))[:, 1]
            thr = float(np.quantile(p_tr, 1 - q))
            p_te = m.predict_proba(np.array([rows[d][0] for d in te]))[:, 1]
            for d, p in zip(te, p_te):
                PRED[q]["DEV"][d] = bool(p >= thr)
        allm = fit([rows[d][0] for d in rows], [rows[d][1] for d in rows])
        p_all = allm.predict_proba(np.array([rows[d][0] for d in rows]))[:, 1]
        PRED[q]["model"], PRED[q]["thr"] = allm, float(np.quantile(p_all, 1 - q))
    return rows


def signal_for(q):
    def f(smp, d):
        if smp.name == "DEV":
            return True if PRED[q]["DEV"].get(d) else None
        key = (smp.name, d)
        if key not in PRED[q]:
            x = features(smp, d)
            PRED[q][key] = x is not None and float(PRED[q]["model"].predict_proba(np.array([x]))[0, 1]) >= PRED[q]["thr"]
        return True if PRED[q][key] else None
    return f


VARIANTS = [{"name": f"LightGBM top {int(q * 100)}%: 10:00 straddle to 15:10", "signal": signal_for(q),
             "trade": lambda smp, d, side, stress=gl.STRESS, late=0: target_trade(smp, d, stress, late), "null": "day",
             "eligible": lambda smp, d: True} for q in (0.10, 0.20)]

if __name__ == "__main__":
    rows = build()
    print("SN262 training rows", len(rows), "positive share", round(float(np.mean([r[1] for r in rows.values()])), 3), flush=True)
    res = slot.evaluate("SN262", VARIANTS, years=("2023", "2024", "2025", "2026"))
    res["training_rows"] = len(rows)
    slot.save(HERE / "results-sn262.json", res)
