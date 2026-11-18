"""EN33 (PLAN4.md): does NIFTY's front future lead the SENSEX index by a minute on SENSEX expiry afternoons?

Minute adaptation only (30-second receipt-clock windows and BANKNIFTY futures are not held: DATA_UNAVAILABLE).
  1. Lead-lag: correlation of SENSEX's next-minute log return with NIFTY future's log return this minute, plain and
     partial (both residualised on SENSEX's own return this minute), 13:00-15:00, pooled over the S-X1 days.
  2. Event markout: |z_leader| >= 2 and 0 <= s x z_follower <= 0.5 (z = 1-minute change / sd of the previous 10),
     then the follower moves in s's direction on the next minute -> decision there; one lot of E03.2's contract pick
     (SENSEX spec, Rs 1,250 room) bought at the next bar's fill and sold 4 bars later (ordinary fills, fees, unfunded).
     Events at least 5 bars apart. Random control: 40 seeds, the same count per day at random minutes and sides.
  FAIL at minute resolution unless lag correlation >= 0.05 AND mean event markout > 0 AND > the random median."""
from __future__ import annotations
import math, random, statistics as st
from dataclasses import replace
import numpy as np
import en_lab4 as L4
import en4_data as D4

SEEDS = 40


def _returns(v):
    r = np.full(len(v), np.nan)
    ok = np.isfinite(v[1:]) & np.isfinite(v[:-1]) & (v[:-1] > 0)
    r[1:][ok] = np.log(v[1:][ok] / v[:-1][ok])
    return r


def _markout(t, i, s):
    sp = L4.spec_of(t); rule = replace(L4.E032, put_mult=1.)
    pick = L4.choose4(sp, t, i, s, rule, 1250., 25000.)
    if not pick or i + 5 >= t.n:
        return None
    j, _, limit = pick
    f1, p1 = L4.executable(sp, t, i + 1, j, "BUY", "ordinary", 1)
    if not f1 or p1 is None or p1 > limit:
        return None
    f2, p2 = L4.executable(sp, t, i + 5, j, "SELL", "ordinary", 1)
    if not f2 or p2 is None:
        return None
    return round((p2 - p1) * sp.lot - L4.fee(sp, p1, sp.lot, True) - L4.fee(sp, p2, sp.lot, False), 2)


def score(tapes):
    xs, ys, zs = [], [], []; events = []; per_day = {}; leaders = {}
    for t in tapes:
        L = D4.leader_future(t.day, "NIFTY"); leaders[t.day] = L
        rL, rF = _returns(L), _returns(t.close)
        w = [i for i in range(t.n - 1) if 780 <= t.minute[i] < 900]
        for i in w:
            if np.isfinite([rL[i], rF[i], rF[i + 1]]).all():
                xs.append(rL[i]); ys.append(rF[i + 1]); zs.append(rF[i])
        last = -99; n = 0
        for i in w:
            if i < last + 5 or i < 12 or i + 1 >= t.n:
                continue
            pL, pF = rL[i - 10:i], rF[i - 10:i]
            if not (np.isfinite(pL).all() and np.isfinite(pF).all() and np.isfinite([rL[i], rF[i], rF[i + 1]]).all()):
                continue
            sL, sF = float(np.std(pL)), float(np.std(pF))
            if sL <= 0 or sF <= 0:
                continue
            zL, zF = rL[i] / sL, rF[i] / sF; s = 1 if zL > 0 else -1
            if abs(zL) >= 2 and 0 <= s * zF <= .5 and s * rF[i + 1] > 0 and t.minute[i + 1] < 900 and L4.available(t, i + 1, s):
                m = _markout(t, i + 1, s)
                if m is not None:
                    events.append(dict(day=t.day, i=i + 1, side=s, markout=m)); last = i; n += 1
        per_day[t.day] = n
    x, y, z = np.array(xs), np.array(ys), np.array(zs)
    corr = float(np.corrcoef(x, y)[0, 1]) if len(x) > 2 else math.nan
    def resid(a, b):
        B = np.vstack([b, np.ones_like(b)]).T; coef = np.linalg.lstsq(B, a, rcond=None)[0]; return a - B @ coef
    pcorr = float(np.corrcoef(resid(x, z), resid(y, z))[0, 1]) if len(x) > 3 else math.nan
    same = float(np.corrcoef(x, z)[0, 1]) if len(x) > 2 else math.nan
    seeds = []
    for s0 in range(SEEDS):
        vals = []
        for t in tapes:
            k = per_day[t.day]
            if not k:
                continue
            rng = random.Random(f"en33-{s0}-{t.day}")
            cand = [i for i in range(t.n - 6) if 781 <= t.minute[i] < 900]
            for i in rng.sample(cand, min(k, len(cand))):
                s = rng.choice((1, -1))
                if L4.available(t, i, s):
                    m = _markout(t, i, s)
                    if m is not None:
                        vals.append(m)
        seeds.append(float(np.mean(vals)) if vals else 0.)
    mean_ev = float(np.mean([e["markout"] for e in events])) if events else math.nan
    rmed = float(st.median(seeds)) if seeds else math.nan
    ok = np.isfinite(corr) and corr >= .05 and np.isfinite(mean_ev) and mean_ev > 0 and mean_ev > rmed
    return dict(minutes=len(x), lag_corr=round(corr, 4), partial_lag_corr=round(pcorr, 4), same_minute_corr=round(same, 4),
                events=len(events), event_mean_markout=round(mean_ev, 2) if np.isfinite(mean_ev) else None,
                event_winners=sum(e["markout"] > 0 for e in events), random_median_markout=round(rmed, 2),
                days=len(tapes), leader_minutes=int(sum(np.isfinite(v[165:]).sum() for v in leaders.values())),
                verdict="PASS" if ok else "FAIL", note="minute adaptation; 30-second and BANKNIFTY versions DATA_UNAVAILABLE",
                sample=events[:5])
