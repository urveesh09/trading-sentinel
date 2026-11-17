"""SN271 - the overnight index ETF (PLAN.md amendment, Nov 16). Buy at 15:20 at the index level, sell on the next trading
day at 09:16 / 09:20 / 09:30; nights (A) weekday, (B) every night, (C) weekday after a down day, (D) weekday after an up day.
Rs 30,000 a night (also Rs 1,01,250). Zerodha's ETF delivery / BTST charges + 0.005% half-spread + 0.01% delay a side.
Index minutes of every trading day (expiry days included): DEV/TEST from SN201's dev cache, EXAM-N from SN221's and
SN201's lean mirrors, EXAM-S from SN201's lean SENSEX mirror. The exams are partly seen for this idea (SN257 printed the
close-to-open drift): disclosed."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402

W30, W101 = 30000.0, 101250.0
H, DELAY = 0.00005, 0.0001
WINDOWS = {"DEV": ("2022-04-01", "2026-08-20"), "TEST": ("2026-08-20", "2026-10-29"), "EXAMN": ("2020-10-01", "2022-03-26"),
           "EXAMS": ("2024-10-01", "2026-05-01")}
YEARS = ("2022", "2023", "2024", "2025", "2026")


def index_minutes(name):
    if name in ("DEV", "TEST"):
        d = gl.wk.dev_data()["idx"]
        return {k: v for k, v in d.items()}
    cfg = gl.SRC[name]
    raw = gl._read_kind(cfg["index"], cfg["und"], "index", "2020-06-01" if name == "EXAMN" else "2024-05-01", cfg["hi"]).get(None, {})
    return {d: a[3] for d, a in raw.items()}


def px(arr, i):
    c = arr[: i + 1]
    ok = np.flatnonzero(~np.isnan(c))
    return None if not len(ok) or i - ok[-1] > 5 else float(c[ok[-1]])


def charges(buy_val, sell_val, stt_both=False):
    exch = 0.0000307 * (buy_val + sell_val)
    sebi = 0.000001 * (buy_val + sell_val)
    gst = 0.18 * (exch + sebi)
    stamp = 0.00015 * buy_val
    stt = 0.001 * (buy_val + sell_val) if stt_both else 0.00001 * sell_val
    return exch + sebi + gst + stamp + stt + 15.34


def night(idx, cal, d, ie, ix, notional, h=H, delay=DELAY, stt_both=False):
    k = cal.index(d)
    if k + 1 >= len(cal):
        return None
    nd = cal[k + 1]
    a, b = px(idx[d], ie), px(idx[nd], ix)
    if a is None or b is None:
        return None
    buy = a * (1 + h + delay)
    sell = b * (1 - h - delay)
    units = notional / buy
    net = units * (sell - buy) - charges(notional, units * sell, stt_both)
    return {"day": d, "exit_day": nd, "net": net, "ret": b / a - 1.0}


def nights_of(kind, idx, cal, d):
    k = cal.index(d)
    if k + 1 >= len(cal):
        return False
    gap = (dt.date.fromisoformat(cal[k + 1]) - dt.date.fromisoformat(d)).days
    if kind == "B":
        return True
    if gap != 1:
        return False
    if kind == "A":
        return True
    if k == 0:
        return False
    p, c = px(idx[cal[k - 1]], 374), px(idx[d], 365)
    if p is None or c is None:
        return False
    return (c < p) if kind == "C" else (c > p)


def book(name, kind, ix, notional=W30, late=0, h=H, delay=DELAY, stt_both=False, days=None):
    idx = INDEX[name]
    cal = sorted(idx)
    lo, hi = WINDOWS[name]
    out = []
    for d in cal:
        if not (lo <= d < hi):
            continue
        if days is not None:
            if d not in days:
                continue
        elif not nights_of(kind, idx, cal, d):
            continue
        t = night(idx, cal, d, 365 + late, ix + late, notional, h, delay, stt_both)
        if t:
            out.append(t)
    return out


INDEX = {}

if __name__ == "__main__":
    out_path = HERE / "results-sn271.json"
    if out_path.exists():
        raise SystemExit("SN271 is run once")
    for n in ("DEV", "TEST"):
        INDEX[n] = index_minutes(n)
    res = {"variants": {}}
    V = [(k, ix) for k in ("A", "B", "C", "D") for ix in (1, 5, 15)]
    for k, ix in V:
        st = gl.stats(book("DEV", k, ix))
        st["maxmin"] = round(gl.maxmin(st))
        st["at_101k"] = gl.stats(book("DEV", k, ix, W101))["net"]
        res["variants"][f"{k} exit {ix}"] = st
        print("SN271", f"{k} exit {ix:2d}", f"nights {st['trades']} net {st['net']} maxmin {st['maxmin']} win {st['win_pct']}% worst {st['worst']} "
              f"at 1.01L {st['at_101k']}", json.dumps(st["by_year"]), flush=True)
    pick = max(V, key=lambda v: (res["variants"][f"{v[0]} exit {v[1]}"]["maxmin"], res["variants"][f"{v[0]} exit {v[1]}"]["net"]))
    pk = f"{pick[0]} exit {pick[1]}"
    pst = res["variants"][pk]
    # G2: only (C)/(D) have a selection; the same-budget null over the C/D variants (random weekday nights, same count)
    idx, cal = INDEX["DEV"], sorted(INDEX["DEV"])
    lo, hi = WINDOWS["DEV"]
    wk_nights = [d for d in cal if lo <= d < hi and nights_of("A", idx, cal, d)]
    rng = np.random.default_rng(271)
    null_sel = []
    cache = {}
    for _ in range(200):
        best = -1e18
        for k, ix in V:
            if k in ("A", "B"):
                v = res["variants"][f"{k} exit {ix}"]["maxmin"]
            else:
                cnt = res["variants"][f"{k} exit {ix}"]["trades"]
                pick_days = rng.choice(len(wk_nights), size=cnt, replace=False)
                by = {y: 0.0 for y in YEARS}
                for p_ in pick_days:
                    d = wk_nights[int(p_)]
                    key = (d, ix)
                    if key not in cache:
                        cache[key] = night(idx, cal, d, 365, ix, W30)
                    t = cache[key]
                    if t and t["exit_day"][:4] in by:
                        by[t["exit_day"][:4]] += t["net"]
                v = min(by.values())
            best = max(best, v)
        null_sel.append(best)
    p95 = float(np.percentile(null_sel, 95))
    g2_na = pick[0] in ("A", "B")
    s2 = gl.stats(book("DEV", pick[0], pick[1], h=2 * H, delay=2 * DELAY))["net"]
    late = gl.stats(book("DEV", pick[0], pick[1], late=1))["net"]
    pess = gl.stats(book("DEV", pick[0], pick[1], stt_both=True))["net"]
    G1 = pst["net"] > 0 and pst["years_positive"] >= 3
    G2 = True if g2_na else pst["maxmin"] > p95
    G4 = s2 > 0 and late > 0
    ex = {}
    for n in ("TEST", "EXAMN", "EXAMS"):
        if n not in INDEX:
            INDEX[n] = index_minutes(n)
        tr = book(n, pick[0], pick[1])
        ex[n] = gl.stats(tr)
        ex[n]["at_101k"] = gl.stats(book(n, pick[0], pick[1], W101))["net"]
        ex[n]["double_cost"] = gl.stats(book(n, pick[0], pick[1], h=2 * H, delay=2 * DELAY))["net"]
        ex[n]["mean_ret_pct"] = round(100 * float(np.mean([t["ret"] for t in tr])), 4) if tr else None
        ex[n]["worst_ret_pct"] = round(100 * float(np.min([t["ret"] for t in tr])), 2) if tr else None
        print("SN271 PICK", pk, n, json.dumps({k: ex[n][k] for k in ("trades", "net", "per_trade", "win_pct", "worst", "by_year", "months_positive",
                                                                      "months", "at_101k", "double_cost", "mean_ret_pct", "worst_ret_pct")}), flush=True)
    G3 = ex["EXAMN"]["net"] > 0 and ex["EXAMS"]["net"] > 0
    verdict = "PASS" if (G1 and G2 and G3 and G4) else ("WATCH" if (G1 and G2 and G3) else "FAIL")
    dev_tr = book("DEV", pick[0], pick[1])
    res.update(pick=pk, pick_dev=pst, null={"selected_maxmin_p95": round(p95), "na": g2_na}, dev_double_cost=s2, dev_late_1=late,
               dev_pessimistic_stt_both_sides=pess, dev_worst_ret_pct=round(100 * float(np.min([t["ret"] for t in dev_tr])), 2),
               dev_mean_ret_pct=round(100 * float(np.mean([t["ret"] for t in dev_tr])), 4), exams=ex,
               gates={"G1": G1, "G2": G2 if not g2_na else "n/a (no selection)", "G3": G3, "G4": G4}, verdict=verdict,
               notes=["exams partly seen for this idea: SN257 printed the close-to-open drift on DEV and both exams before this slot was written"])
    print("SN271 VERDICT", verdict, json.dumps(res["gates"]), "DEV double cost", s2, "late", late, "STT both sides", pess, flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
