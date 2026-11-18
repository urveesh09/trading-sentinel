"""All-session minutes for round 7 (PLAN7.md), read-only from the Breeze history database.

For every session with index minutes: the index (09:15-15:29) and the dated FRONT future (the nearest expiry on or after
the session that has >= 300 minutes that day; a monthly contract stays front through its own expiry day). Arrays are
375 bars labelled by bar start (bar k ends at minute 556 + k). Cached once per database state (row counts + a content
hash are recorded in the manifest that the freeze binds). Also: daily bars from the index minutes, the pinned engine's
ADX(14), 5-minute futures frames for the pinned N11 dispatcher, and the time-adjusted participation reading."""
from __future__ import annotations
import hashlib, json, sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
DB = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
LAST_FUT = {"NIFTY": "2026-10-28", "SENSEX": "2026-10-28"}     # Breeze futures end (request 7 covers what follows)


def _con():
    return sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)


def _k(stamp):
    return (int(stamp[11:13]) - 9) * 60 + int(stamp[14:16]) - 15


def build(und):
    """{'dates': [...], 'X': (n,375,4), 'F': (n,375,5), 'front': [...], 'manifest': {...}} cached in _local."""
    c = _con()
    ndx = c.execute("SELECT count(*), max(datetime) FROM candles WHERE kind='index' AND underlying=? AND interval='1minute'", (und,)).fetchone()
    nfu = c.execute("SELECT count(*), max(datetime) FROM candles WHERE kind='future' AND underlying=? AND interval='1minute'", (und,)).fetchone()
    key = hashlib.sha256(json.dumps([und, ndx, nfu]).encode()).hexdigest()[:12]
    cache = LOCAL / f"fut7-{und}-{key}.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        return dict(dates=[str(d) for d in z["dates"]], X=z["X"], F=z["F"], front=[str(x) for x in z["front"]],
                    manifest=json.loads(str(z["manifest"])))
    days = {}
    for stamp, o, h, l, cl in c.execute("SELECT datetime, open, high, low, close FROM candles WHERE kind='index' AND underlying=? "
                                        "AND interval='1minute' ORDER BY datetime", (und,)):
        k = _k(stamp)
        if 0 <= k < 375 and all(v is not None and v > 0 for v in (o, h, l, cl)):
            days.setdefault(stamp[:10], np.full((375, 4), np.nan))[k] = (o, h, l, cl)
    exps, last = [], ""
    while True:
        r = c.execute("SELECT expiry FROM candles WHERE kind='future' AND underlying=? AND expiry>? ORDER BY expiry LIMIT 1", (und, last)).fetchone()
        if not r:
            break
        last = r[0]; exps.append(last)
    count = {}
    for e in exps:
        for d, n in c.execute("SELECT substr(datetime,1,10), count(*) FROM candles WHERE kind='future' AND underlying=? AND expiry=? "
                              "AND interval='1minute' GROUP BY 1", (und, e)):
            count[(e, d)] = n
    front = {}
    for d in days:
        cands = sorted(e for e in exps if e >= d and count.get((e, d), 0) >= 300)
        front[d] = cands[0] if cands else ""
    fut = {d: np.full((375, 5), np.nan) for d in days}
    for e in exps:
        mine = {d for d, f in front.items() if f == e}
        if not mine:
            continue
        for stamp, o, h, l, cl, v in c.execute("SELECT datetime, open, high, low, close, volume FROM candles WHERE kind='future' AND underlying=? "
                                               "AND expiry=? AND interval='1minute'", (und, e)):
            d = stamp[:10]; k = _k(stamp)
            if d in mine and 0 <= k < 375 and all(x is not None and x > 0 for x in (o, h, l, cl)) and v is not None and v >= 0:
                fut[d][k] = (o, h, l, cl, v)
    c.close()
    dates = sorted(days)
    X = np.stack([days[d] for d in dates]); F = np.stack([fut[d] for d in dates]); fr = [front[d] for d in dates]
    h = hashlib.sha256(np.nan_to_num(X, nan=-1).tobytes() + np.nan_to_num(F, nan=-1).tobytes() + "|".join(fr).encode()).hexdigest()
    man = dict(und=und, index_rows=ndx, future_rows=nfu, sessions=len(dates), with_front=sum(1 for x in fr if x), content_sha256=h)
    LOCAL.mkdir(exist_ok=True)
    np.savez(cache, dates=np.array(dates), X=X, F=F, front=np.array(fr), manifest=np.array(json.dumps(man)))
    return dict(dates=dates, X=X, F=F, front=fr, manifest=man)


_S = {}


def store(und):
    if und not in _S:
        s = build(und); s["pos"] = {d: i for i, d in enumerate(s["dates"])}; _S[und] = s
    return _S[und]


def covered(und, d, need_future=True):
    s = store(und); i = s["pos"].get(d)
    if i is None:
        return False
    okx = np.isfinite(s["X"][i, 165:, 3]).sum() >= 200
    return okx and (not need_future or (bool(s["front"][i]) and np.isfinite(s["F"][i, 165:, 3]).sum() >= 200))


_PS = {}


def prior_sessions(und, d, n, need_future=True):
    """The n covered sessions strictly before d (oldest first), or None if fewer exist."""
    key = (und, d, n, need_future)
    if key not in _PS:
        _PS[key] = _prior(und, d, n, need_future)
    return _PS[key]


def _prior(und, d, n, need_future):
    s = store(und); i = s["pos"].get(d, int(np.searchsorted(np.array(s["dates"]), d)))
    out = []
    for j in range(i - 1, -1, -1):
        if covered(und, s["dates"][j], need_future):
            out.append(s["dates"][j])
            if len(out) == n:
                return out[::-1]
    return None


# ---------------------------------------------------------------- daily bars, ADX (the pinned engine's formula)
def daily_frame(und="NIFTY"):
    import pandas as pd
    s = store(und); rows = []
    for d, x in zip(s["dates"], s["X"]):
        ok = np.isfinite(x[:, 3])
        if ok.sum() >= 300:
            rows.append((pd.Timestamp(d), float(x[ok][0, 0]), float(np.nanmax(x[:, 1])), float(np.nanmin(x[:, 2])), float(x[ok][-1, 3])))
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close"]).set_index("date")


_ADX = {}


def adx_before(day, und="NIFTY"):
    """The pinned fno_book.daily_adx: ADX(14) of the last daily bar before `day` (index minutes -> daily bars)."""
    if (und, day) not in _ADX:
        import n11x
        fb = n11x.engine()["fno_book"]
        v, _ = fb.daily_adx(daily_frame(und), date.fromisoformat(day))
        _ADX[(und, day)] = v
    return _ADX[(und, day)]


# ---------------------------------------------------------------- 5-minute futures frames (N11 / participation)
def frame5(und, day, cal_days=21):
    """5-minute front-future bars (naive IST datetime index = bar start) for the sessions in [day - cal_days, day].
    Each session uses its own front contract, as the research's frames did."""
    import pandas as pd
    s = store(und); lo = (date.fromisoformat(day) - timedelta(days=cal_days)).isoformat(); rows = []
    for d in s["dates"]:
        if not lo <= d <= day:
            continue
        F = s["F"][s["pos"][d]]
        for b in range(0, 375, 5):
            w = F[b:b + 5]
            ok = np.isfinite(w[:, 3])
            if not ok.any():
                continue
            w = w[ok]; m = 555 + b                                       # minutes since midnight of the bar start
            rows.append((datetime.fromisoformat(d) + timedelta(minutes=m), float(w[0, 0]), float(w[:, 1].max()), float(w[:, 2].min()),
                         float(w[-1, 3]), float(w[:, 4].sum())))
    return pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")


_RV = {}


def rvol5(day):
    """{decision minute (bar end, minutes since midnight): time-adjusted volume of the last closed 5-minute NIFTY future
    bar} by the pinned engine's _rvol_time_adjusted (SENSEX reads NIFTY's participation, as the shipped signal does)."""
    if day not in _RV:
        import n11x
        mom = n11x.engine()["fno_engine_mom"]
        fr = frame5("NIFTY", day, 15); out = {}
        today = fr[fr.index.date == date.fromisoformat(day)]
        for ts in today.index:
            m = ts.hour * 60 + ts.minute + 5
            if 780 <= m <= 900:
                v = mom._rvol_time_adjusted(fr[fr.index <= ts], ts)
                out[m] = float(v) if v is not None else float("nan")
        _RV[day] = out
    return _RV[day]
