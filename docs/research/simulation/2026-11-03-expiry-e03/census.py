"""Hero-move census on the seen NIFTY 2024/2025 expiry minute chains. Diagnosis only.

Entry is the next bar's open plus the frozen half spread; the outcome is the best later
close minus the half spread (a close the ticket could have been sold at, not a bar high).
Strikes are limited to four steps from the index: the download holds every strike within
four steps of the day's low and high, so wider strikes would exist only on days that later
moved there (look-ahead). 2023 is never opened.
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
E02 = HERE.parent / "2026-11-03-expiry-e02"
sys.path.insert(0, str(E02))
import data as D          # noqa: E402
import e02_lab as E       # noqa: E402

MAX_STEPS = 4


def strike_cover(t):
    """Is every strike within MAX_STEPS of the index present all afternoon? (structure, no outcome)"""
    have = {(float(k), int(o)) for k, o in zip(t.strikes, t.kinds)}
    bad = 0
    for i in range(int(np.searchsorted(t.minute, 780)), int(np.searchsorted(t.minute, 900))):
        c = t.close[i]
        if not np.isfinite(c):
            continue
        atm = round(c / 50) * 50
        for s in range(1, MAX_STEPS + 1):
            bad += (float(atm + 50 * s), 1) not in have
            bad += (float(atm - 50 * s), -1) not in have
    return bad


def realized(t, i, n=60):
    c = t.close[max(0, i - n):i + 1]
    c = c[np.isfinite(c)]
    if len(c) < n // 2:
        return np.nan
    r = np.diff(np.log(c))
    return float(np.std(r) * math.sqrt(375 * 252))


def census(year):
    tapes = D.load_year(year, exam=year == 2024)
    rows = []
    for t in tapes:
        lo_i, hi_i = int(np.searchsorted(t.minute, 780)), int(np.searchsorted(t.minute, 900))
        flat = int(np.searchsorted(t.minute, 928))
        best = dict(mult=0.0)
        hits = {3: 0, 5: 0, 10: 0}
        tickets = 0
        for i in range(lo_i, hi_i):
            c = t.close[i]
            if not np.isfinite(c) or i + 1 >= t.n:
                continue
            for j in range(len(t.strikes)):
                d = int(t.kinds[j])
                dist = d * (t.strikes[j] - c)
                if dist <= 0 or dist > MAX_STEPS * 50:
                    continue
                ask = t.q[i, j, 3]
                if not np.isfinite(ask) or not 1.0 <= ask <= 20.0:
                    continue
                o = t.q[i + 1, j, 0]
                if not np.isfinite(o):
                    continue
                entry = E.up(o + E.half(o))
                later = t.q[i + 2:flat + 1, j, 3]
                later = later[np.isfinite(later)]
                if not len(later):
                    continue
                exit_best = max(E.down(x - E.half(x)) for x in later)
                m = exit_best / entry
                tickets += 1
                for k in hits:
                    hits[k] += m >= k
                if m > best["mult"]:
                    best = dict(mult=round(m, 2), minute=int(t.minute[i]), strike=float(t.strikes[j]), kind=d,
                                entry=entry, dist=float(dist))
        x = t.close
        m13 = x[lo_i]
        afternoon = x[lo_i:flat + 1]
        afternoon = afternoon[np.isfinite(afternoon)]
        morning = x[:lo_i][np.isfinite(x[:lo_i])]
        rows.append(dict(day=t.day, cover_missing=strike_cover(t), tickets=tickets, best=best,
                         share3=round(hits[3] / tickets, 4) if tickets else None,
                         share5=round(hits[5] / tickets, 4) if tickets else None,
                         share10=round(hits[10] / tickets, 4) if tickets else None,
                         pm_range=round(float(afternoon.max() - afternoon.min()), 1),
                         pm_move=round(float(afternoon[-1] - m13), 1),
                         am_range=round(float(morning.max() - morning.min()), 1),
                         am_move=round(float(morning[-1] - morning[0]), 1),
                         rv60_1300=round(realized(t, lo_i), 4)))
        print(year, t.day, rows[-1]["best"].get("mult"), rows[-1]["pm_range"], flush=True)
    return rows


if __name__ == "__main__":
    out = {str(y): census(y) for y in (2024, 2025)}
    D.dump(HERE / "census.json", out)
