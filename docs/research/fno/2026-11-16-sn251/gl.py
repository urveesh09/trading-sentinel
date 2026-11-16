"""SN251-SN275 gap-leg lab (PLAN.md section 2). Sessions in SN01's format for every sample; bought-option positions
valued minute by minute (and across nights) at executable prices; one-lot standalone books; statistics.

Samples:
  DEV    NIFTY 2022-04-01 .. 2026-08-19 (SN186's 2022 dataset via sn01_data.build_year; SN01's 2023-2026 caches)
  TEST   NIFTY 2026-08-20 .. 2026-10-28
  EXAMN  NIFTY Oct 2020 - Mar 2022 (SN221 / SN211 full option mirrors, SN221 / SN201 lean index mirrors, SN221 futures)
  EXAMS  SENSEX Oct 2024 - Apr 2026 (SN211 full option mirror, SN201 lean index mirror, SN221 futures)
Prices: a buy fills at close + half the P75 spread (wk table, SENSEX scaled), a sale at close - half; an option close older
than LOOK minutes is no price. Costs: wk.charges (Zerodha's schedule of the exchange) + STRESS per lot per leg per round
trip. Stops are checked on minute closes and fill at that minute's bid; overnight positions are valued on the next session.
"""
from __future__ import annotations

import bisect
import datetime as _dt
import hashlib
import json
import math
import pickle
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
LOCAL = HERE / "_local"
sys.path.insert(0, str(FNO / "2026-11-14-sn201"))
sys.path.insert(0, str(FNO / "2026-11-12-sn01"))
import wk  # noqa: E402
import sn01_data as D  # noqa: E402

INST = {"NIFTY": wk.NIFTY, "SENSEX": wk.SENSEX}
NM = 375
STRESS = 205.0
LOOK = 10
FLAT = 355                      # 15:10
I = {"09:16": 1, "09:20": 5, "09:30": 15, "09:45": 30, "10:00": 45, "10:15": 60, "11:00": 105, "13:00": 225, "14:00": 285,
     "15:10": 355, "15:15": 360, "15:20": 365, "15:25": 370}
DEV_LO, TEST_LO, TEST_HI = "2022-04-01", "2026-08-20", "2026-10-29"
DATA_2022 = FNO / "2026-11-13-sn186/_local/dataset-nifty-2022"
SRC = {
    "EXAMN": {"und": "NIFTY", "lo": "2020-10-01", "hi": "2022-03-25",
              "option": [FNO / "2026-11-15-sn221/_local/mirror-nifty-2021-full.sqlite", FNO / "2026-11-14-sn211/_local/mirror-nifty-exam-full.sqlite"],
              "index": [FNO / "2026-11-15-sn221/_local/mirror-nifty-2021-lean.sqlite", FNO / "2026-11-14-sn201/_local/mirror-nifty-exam.sqlite"],
              "future": [FNO / "2026-11-15-sn221/_local/fut-nifty-2021.sqlite", FNO / "2026-11-15-sn221/_local/fut-nifty-2122.sqlite"]},
    "EXAMS": {"und": "SENSEX", "lo": "2024-10-01", "hi": "2026-04-30",
              "option": [FNO / "2026-11-14-sn211/_local/mirror-sensex-exam-full.sqlite"],
              "index": [FNO / "2026-11-14-sn201/_local/mirror-sensex-exam.sqlite"],
              "future": [FNO / "2026-11-15-sn221/_local/fut-sensex.sqlite"]},
}
ADX_FILE = FNO / "2026-11-12-sn06/_local/daily.json"


# ---- reading -------------------------------------------------------------------------------------------------
def _minute(stamp):
    return int(stamp[11:13]) * 60 + int(stamp[14:16]) - 555


def _ffill(a):
    out = a.copy()
    last = np.nan
    for i in range(len(out)):
        if np.isnan(out[i]):
            out[i] = last
        else:
            last = out[i]
    first = np.flatnonzero(~np.isnan(out))
    if len(first):
        out[: first[0]] = out[first[0]]
    return out


def _con(path):
    return sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)


def _where(con, und):
    cols = [r[1] for r in con.execute("PRAGMA table_info(candles)")]
    w, a = "", ()
    if "underlying" in cols:
        w, a = " AND underlying=?", (und,)
    if "interval" in cols:
        w += " AND interval='1minute'"
    return w, a


def _read_kind(paths, und, kind, lo, hi):
    """{key: {day: (5, NM) array}} with key = None (index), expiry (future) or (expiry, strike, opt) (option)."""
    out = {}
    for p in paths:
        con = _con(p)
        w, a = _where(con, und)
        sel = "expiry, strike, opt, " if kind == "option" else ("expiry, " if kind == "future" else "")
        q = (f"SELECT {sel}datetime, open, high, low, close, volume FROM candles WHERE kind=?{w} AND datetime >= ? AND datetime < ?")
        for row in con.execute(q, (kind,) + a + (lo, hi + "~")):
            if kind == "option":
                e, k, o, stamp = row[0][:10], int(round(float(row[1]))), row[2], row[3]
                key, vals = (e, k, o), row[4:]
            elif kind == "future":
                key, stamp, vals = row[0][:10], row[1], row[2:]
            else:
                key, stamp, vals = None, row[0], row[1:]
            m = _minute(stamp)
            if not (0 <= m < NM) or vals[3] is None:
                continue
            d = stamp[:10]
            arr = out.setdefault(key, {}).get(d)
            if arr is None:
                arr = np.full((5, NM), np.nan)
                out[key][d] = arr
            arr[:, m] = [np.nan if v is None else float(v) for v in vals[:4]] + [float(vals[4] or 0.0)]
        con.close()
    return out


def _daily_from(index_by_day):
    bars = {}
    for d, a in sorted(index_by_day.items()):
        c = a[3]
        ok = ~np.isnan(c)
        if ok.sum() < 30:
            continue
        bars[d] = (float(a[0][ok][0]), float(np.nanmax(a[1])), float(np.nanmin(a[2])), float(c[ok][-1]))
    return bars


def build_exam(name):
    """SN01-format sessions of one exam sample (non-expiry days with options of the nearest weekly contract)."""
    cfg = SRC[name]
    lo_idx = (_dt.date.fromisoformat(cfg["lo"]) - _dt.timedelta(days=150)).isoformat()
    idx = _read_kind(cfg["index"], cfg["und"], "index", lo_idx, cfg["hi"]).get(None, {})
    fut = _read_kind(cfg["future"], cfg["und"], "future", cfg["lo"], cfg["hi"])
    opt_rows = _read_kind(cfg["option"], cfg["und"], "option", cfg["lo"], cfg["hi"])
    by_day = {}
    for (e, k, o), days in opt_rows.items():
        for d, arr in days.items():
            if d >= e:
                continue
            by_day.setdefault(d, {}).setdefault(e, {})[(k, o)] = arr
    daily = _daily_from(idx)
    cal = sorted(daily)
    fut_exp = sorted(fut)
    sessions = {}
    for d in sorted(by_day):
        if not (cfg["lo"] <= d <= cfg["hi"]) or d not in idx:
            continue
        e = min(by_day[d])
        front = next((x for x in fut_exp if x >= d and d in fut[x]), None)
        s = {"day": d, "expiry": e, "inst": cfg["und"]}
        ia = idx[d].copy()
        s["index_traded"] = ~np.isnan(ia[3])
        for k in range(4):
            ia[k] = _ffill(ia[k])
        ia[4] = np.nan_to_num(ia[4])
        s["index"] = ia
        if front is not None:
            fa = fut[front][d].copy()
            s["future_traded"] = ~np.isnan(fa[3])
            for k in range(4):
                fa[k] = _ffill(fa[k])
            fa[4] = np.nan_to_num(fa[4])
            if np.isnan(fa[3]).all():
                fa = ia.copy()
            s["future"] = fa
        else:
            s["future"] = ia.copy()
            s["future_traded"] = np.zeros(NM, dtype=bool)
        s["options"] = {key: arr.astype(np.float32) for key, arr in by_day[d][e].items()}
        prev = [x for x in cal if x < d]
        s["prev"] = daily[prev[-1]] if prev else None
        s["prev_days"] = [daily[x] for x in prev[-25:]]
        if np.isnan(s["index"][3]).all():
            continue
        sessions[d] = s
    return {"name": name, "inst": cfg["und"], "sessions": sessions, "daily": daily, "cal": cal}


def build_dev():
    """NIFTY Apr 2022 - Oct 28 2026 sessions (DEV + TEST), with the calendar and daily bars of every index day."""
    sessions = {}
    D.DATASETS["2022"] = DATA_2022
    s22 = D.build_year("2022")["sessions"]
    for d, s in s22.items():
        if d >= DEV_LO:
            sessions[d] = s
    for y in ("2023", "2024", "2025", "2026"):
        sessions.update(D.load_year(y)["sessions"])
    for s in sessions.values():
        s["inst"] = "NIFTY"
    daily = {}
    for y, p in list(wk.DEV_SOURCES.items()):
        idx = _read_kind([p], "NIFTY", "index", f"{y}-01-01", f"{y}-12-31").get(None, {})
        for d, b in _daily_from(idx).items():
            if d[:4] == y:
                daily[d] = b
    return {"name": "DEVALL", "inst": "NIFTY", "sessions": sessions, "daily": daily, "cal": sorted(daily)}


def _cache(name, build):
    LOCAL.mkdir(exist_ok=True)
    p = LOCAL / f"gl-{name}.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    x = build()
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(x, protocol=pickle.HIGHEST_PROTOCOL))
    tmp.replace(p)
    return x


SEALED = {"EXAMN": False, "EXAMS": False}       # SN254+ open an exam only for a committed pick


class Sample:
    def __init__(self, name, raw, lo=None, hi=None):
        self.name, self.inst = name, raw["inst"]
        self.mk = INST[self.inst]
        self.daily, self.cal = raw["daily"], raw["cal"]
        self.days = sorted(d for d in raw["sessions"] if (lo is None or d >= lo) and (hi is None or d < hi))
        self.s = {d: raw["sessions"][d] for d in self.days}
        self._adx = None

    def next_day(self, d):
        """The next trading day of the calendar (expiry days included)."""
        k = bisect.bisect_right(self.cal, d)
        return self.cal[k] if k < len(self.cal) else None

    def sessions_until(self, d, e):
        return max(0, bisect.bisect_right(self.cal, e) - bisect.bisect_right(self.cal, d))

    def prev_bar(self, d, back=1):
        k = bisect.bisect_left(self.cal, d) - back
        return self.daily[self.cal[k]] if k >= 0 else None

    def adx(self, d):
        if self._adx is None:
            self._adx = adx_table(self)
        r = self._adx.get(d)
        return None if r is None else r["adx"]


def sample(name):
    if name in ("DEV", "TEST"):
        raw = _cache("devall", build_dev)
        return Sample(name, raw, *((DEV_LO, TEST_LO) if name == "DEV" else (TEST_LO, TEST_HI)))
    if name in SEALED and not SEALED[name]:
        raise SystemExit(f"{name} is sealed: a slot opens it only for its committed pick")
    return Sample(name, _cache(name.lower(), lambda: build_exam(name)))


def adx_table(smp):
    """Yesterday's daily ADX(14) and DMI direction, SN06's exact algorithm. DEV uses SN06's own file for 2023+ (Gold's
    gate) and this computation on the 2022 bars before it."""
    bars = [[d, *smp.daily[d]] for d in smp.cal]
    out, n = {}, 14
    tr_s = pdm_s = mdm_s = adx = None
    dx_hist = []
    for k in range(1, len(bars)):
        _, _, h, l, c = bars[k]
        _, _, ph, pl, pc = bars[k - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up, dn = h - ph, pl - l
        pdm = up if up > dn and up > 0 else 0.0
        mdm = dn if dn > up and dn > 0 else 0.0
        if tr_s is None:
            tr_s, pdm_s, mdm_s = tr, pdm, mdm
        else:
            tr_s, pdm_s, mdm_s = tr_s - tr_s / n + tr, pdm_s - pdm_s / n + pdm, mdm_s - mdm_s / n + mdm
        pdi, mdi = 100 * pdm_s / tr_s, 100 * mdm_s / tr_s
        dx = 100 * abs(pdi - mdi) / max(pdi + mdi, 1e-9)
        dx_hist.append(dx)
        if len(dx_hist) == n:
            adx = sum(dx_hist) / n
        elif adx is not None:
            adx = (adx * (n - 1) + dx) / n
        if k + 1 < len(bars) and k >= 2 * n:
            out[bars[k + 1][0]] = {"adx": round(adx, 2), "dir": 1 if pdi >= mdi else -1}
    if smp.name in ("DEV", "TEST"):
        official = json.loads(ADX_FILE.read_text(encoding="utf-8"))
        out = {d: r for d, r in out.items() if d < "2023-01-01"}
        out.update(official)
    return out


# ---- prices and positions --------------------------------------------------------------------------------------
def opx(s, k, o, i, look=LOOK):
    a = s["options"].get((k, o))
    if a is None or i < 0:
        return None
    c = a[3][max(0, i - look): i + 1]
    ok = np.flatnonzero(~np.isnan(c))
    return None if not len(ok) else float(c[ok[-1]])


def atm(smp, s, i):
    st = smp.mk["step"]
    return int(round(float(s["index"][3][i]) / st) * st)


class Pos:
    """A bought (or, for Tier B, sold) option position. legs = [(strike, 'CE'|'PE', +1 buy / -1 sell)]."""

    def __init__(self, smp, s, legs, i, lots=1, stress=STRESS):
        self.smp, self.mk = smp, smp.mk
        self.legs, self.lots, self.stress = legs, lots, stress
        self.qty = lots * self.mk["lot"]
        self.day, self.i, self.expiry = s["day"], i, s["expiry"]
        self.fills = []
        for k, o, sg in legs:
            p = opx(s, k, o, i)
            if p is None:
                self.fills = None
                return
            self.fills.append(wk.ask(self.mk, p) if sg > 0 else wk.bid(self.mk, p))

    @property
    def ok(self):
        return self.fills is not None

    @property
    def premium(self):
        return sum(f * sg for (_k, _o, sg), f in zip(self.legs, self.fills)) * self.qty

    def value(self, s, j, look=LOOK):
        """Net rupees if closed at minute j of session s (same contract), or None."""
        if s["expiry"] != self.expiry:
            return None
        tot = fees = 0.0
        for (k, o, sg), f in zip(self.legs, self.fills):
            p = opx(s, k, o, j, look)
            if p is None:
                return None
            if sg > 0:
                x = wk.bid(self.mk, p)
                tot += (x - f) * self.qty
                fees += wk.charges(f, x, self.qty, self.mk["exch"])
            else:
                x = wk.ask(self.mk, p)
                tot += (f - x) * self.qty
                fees += wk.charges(x, f, self.qty, self.mk["exch"])
        return tot - fees - self.stress * self.lots * len(self.legs)


def walk(pos, s, j0, j1, room=None, stop_index=None, tgt=None):
    """Hold from minute j0 (exclusive) to j1 on session s. Returns (net, minute, reason) or (None, None, 'no price').
    room: stop at -room rupees; stop_index: f(j) -> True to exit; tgt: exit at +tgt rupees."""
    last = None
    for j in range(j0 + 1, j1 + 1):
        v = pos.value(s, j)
        if v is None:
            continue
        last = (v, j)
        if room is not None and v <= -room:
            return v, j, "stop"
        if tgt is not None and v >= tgt:
            return v, j, "target"
        if stop_index is not None and stop_index(j):
            return v, j, "index stop"
    if last is None:
        return None, None, "no price"
    return last[0], last[1], "time"


# ---- books and statistics ------------------------------------------------------------------------------------
def book(smp, rule, **kw):
    """Run rule(smp, d, **kw) -> trade dict {'day','exit_day','net',...} or None over every session; one position at a
    time (a trade blocks sessions up to its exit day)."""
    out, busy_until = [], ""
    for d in smp.days:
        if d < busy_until:               # a position held to a later session blocks the sessions before its exit day
            continue
        t = rule(smp, d, **kw)
        if t and t.get("net") is not None:
            out.append(t)
            busy_until = t.get("exit_day", d)
    return out


def stats(trades, smp_name=""):
    nets = np.array([t["net"] for t in trades], dtype=float)
    by_year, by_month, by_day = {}, {}, {}
    for t in trades:
        x = t["exit_day"]
        by_year[x[:4]] = by_year.get(x[:4], 0.0) + t["net"]
        by_month[x[:7]] = by_month.get(x[:7], 0.0) + t["net"]
        by_day[x] = by_day.get(x, 0.0) + t["net"]
    srt = np.sort(nets)[::-1]
    m = np.array(list(by_month.values())) if by_month else np.zeros(0)
    return {"trades": len(trades), "net": round(float(nets.sum())) if len(nets) else 0,
            "per_trade": round(float(nets.mean()), 1) if len(nets) else 0.0,
            "win_pct": round(100.0 * float((nets > 0).mean()), 1) if len(nets) else 0.0,
            "worst": round(float(nets.min())) if len(nets) else 0, "best": round(float(nets.max())) if len(nets) else 0,
            "without_best5": round(float(srt[5:].sum())) if len(nets) else 0,
            "by_year": {y: round(v) for y, v in sorted(by_year.items())},
            "years_positive": sum(v > 0 for v in by_year.values()), "years": len(by_year),
            "months_positive": int((m > 0).sum()), "months": len(m), "worst_month": round(float(m.min())) if len(m) else 0}


def maxmin(st, years=("2022", "2023", "2024", "2025", "2026")):
    """The worst DEV year (a year without trades counts 0)."""
    return min(st["by_year"].get(y, 0) for y in years)


def sha(path, n=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(n)
            if not b:
                break
            h.update(b)
    return h.hexdigest()
