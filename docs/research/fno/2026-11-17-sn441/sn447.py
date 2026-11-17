"""SN447: the bank-results screen from the auditor's 15 NSE filing timestamps (PLAN.md section 1, frozen at f56f5807;
details fixed here before any number). Screen only; INSUFFICIENT below 20 independent reaction sessions.

Events: nse-bank-filings-pilot.csv. Duplicate issuer-dates keep the first release (a SAME_ISSUER_DATE_REVIEW row is dropped).
Reaction session: the first session whose 09:15 opening is after the filing time (a filing between 09:15 and 15:30 of a
session is flagged IN_SESSION; its reaction session is still the next one). Overlap is counted by reaction session.
Bars: Kite 15-minute (labelled by start) and daily, Jan - Jul 2026 (docs/research/kite/2026-10-05-momentum-h1/_local/raw).
  prev close   the previous session's daily close
  R1           prev close -> close of the 09:30 bar (09:45): the gap plus two completed bars
  R2a / R2b    09:45 -> close of the 11:30 bar (11:45) / of the 15:15 bar (15:30)
  abnormal     stock - beta x NIFTY 50 over the same window; beta = OLS on the prior 60 daily returns
Control: the same stock's 10 ordinary sessions (no own reaction session within +-1 session) nearest in |abnormal R1|.
Statistic: continuation = sign(abn R1) x abn R2. Event mean against the matched-control mean; per reaction session first.
NIFTY mapping: on each reaction session, sign(sum of w x abn R1) with fixed approximate NIFTY weights (HDFCBANK 0.13,
ICICIBANK 0.09, SBIN 0.03, AXISBANK 0.03, KOTAKBANK 0.025) against NIFTY's own R2a; priced with op.leg (HONEST clock,
decision 09:45 = m 30, 1-ITM front weekly, out at 11:45 or the Rs 3,000 stop) on gl's sessions, Rs 205 / 400.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn396"))
OUT = HERE / "results-sn447.json"
RAW = FNO.parent / "kite" / "2026-10-05-momentum-h1" / "_local" / "raw"
BANKS = ("HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK", "KOTAKBANK")
W = {"HDFCBANK": 0.13, "ICICIBANK": 0.09, "SBIN": 0.03, "AXISBANK": 0.03, "KOTAKBANK": 0.025}
IDX = "NIFTY%2050"


def bars15(sym):
    out = {}
    for f in sorted(RAW.glob(f"{sym}_15minute_*.json")):
        for t, o, h, l, c, v in json.loads(f.read_text(encoding="utf-8"))["data"]["candles"]:
            out.setdefault(t[:10], {})[t[11:16]] = c
    return out


def daily(sym):
    f = next(RAW.glob(f"{sym}_day_*.json"))
    return {t[:10]: c for t, o, h, l, c, v in json.loads(f.read_text(encoding="utf-8"))["data"]["candles"]}


def windows(b, prev):
    if prev is None or "09:30" not in b or "11:30" not in b or "15:15" not in b:
        return None
    p45 = b["09:30"]
    return {"R1": p45 / prev - 1, "R2a": b["11:30"] / p45 - 1, "R2b": b["15:15"] / p45 - 1}


def main():
    if OUT.exists():
        raise SystemExit("SN447 is run once")
    ib, idd = bars15(IDX), daily(IDX)
    sessions = sorted(d for d in ib if "09:15" in ib[d])
    ev = []
    seen = set()
    for r in csv.DictReader((HERE / "nse-bank-filings-pilot.csv").open(encoding="utf-8")):
        t = dt.datetime.fromisoformat(r["exchange_disseminated_at_ist"])
        key = (r["symbol"], t.date().isoformat())
        if r["screen_status"] != "RESULT_CANDIDATE" or key in seen:
            continue
        seen.add(key)
        d0 = t.date().isoformat()
        hm = t.strftime("%H:%M")
        in_sess = d0 in sessions and "09:15" <= hm < "15:30"
        react = next(s for s in sessions if s > d0 or (s == d0 and hm < "09:15"))
        ev.append({"symbol": r["symbol"], "filed": r["exchange_disseminated_at_ist"], "in_session": in_sess, "reaction": react})
    data = {s: (bars15(s), daily(s)) for s in BANKS}
    dsess = sorted(idd)

    def prev_close(dd, d):
        k = [x for x in dsess if x < d]
        return dd.get(k[-1]) if k else None

    def beta(dd, d):
        k = [x for x in dsess if x < d][-61:]
        rs = [(dd[b] / dd[a] - 1, idd[b] / idd[a] - 1) for a, b in zip(k, k[1:]) if a in dd and b in dd]
        if len(rs) < 30:
            return 1.0
        x = np.array([q for _p, q in rs])
        y = np.array([p for p, _q in rs])
        return float(np.cov(x, y)[0, 1] / np.var(x, ddof=1))

    def abn(sym, d):
        b, dd = data[sym]
        if d not in b or d not in ib:
            return None
        ws = windows(b[d], prev_close(dd, d))
        wi = windows(ib[d], prev_close(idd, d))
        if ws is None or wi is None:
            return None
        be = beta(dd, d)
        return {k: ws[k] - be * wi[k] for k in ws} | {"beta": be, "idx": wi}
    own = {}
    for e in ev:
        own.setdefault(e["symbol"], set()).add(e["reaction"])
    rows = []
    for e in ev:
        a = abn(e["symbol"], e["reaction"])
        if a is None:
            e["state"] = "NO_BARS"
            rows.append(e)
            continue
        e.update(state="OK", abn={k: round(v, 5) for k, v in a.items() if k in ("R1", "R2a", "R2b")}, beta=round(a["beta"], 3))
        blocked = set()
        for rd in own[e["symbol"]]:
            k = sessions.index(rd)
            blocked |= set(sessions[max(0, k - 1): k + 2])
        ctrl = []
        for d in sessions:
            if d in blocked or d < "2026-01-02":
                continue
            c = abn(e["symbol"], d)
            if c is not None:
                ctrl.append((abs(abs(c["R1"]) - abs(a["R1"])), d, c))
        ctrl.sort(key=lambda z: (z[0], z[1]))
        cs = [z[2] for z in ctrl[:10]]
        for w in ("R2a", "R2b"):
            e[f"cont_{w}"] = round(float(np.sign(a["R1"]) * a[w]), 5)
            e[f"ctrl_cont_{w}"] = round(float(np.mean([np.sign(c["R1"]) * c[w] for c in cs])), 5)
        e["ctrl_mean_absR1"] = round(float(np.mean([abs(c["R1"]) for c in cs])), 5)
        rows.append(e)
    ok = [r for r in rows if r["state"] == "OK"]
    by = {}
    for r in ok:
        by.setdefault(r["reaction"], []).append(r)
    res = {"events": len(ev), "ok": len(ok), "reaction_sessions": len(by), "in_session_filings": sum(r["in_session"] for r in ev),
           "sessions": {d: [r["symbol"] for r in v] for d, v in sorted(by.items())}}
    for w in ("R2a", "R2b"):
        ses = [(np.mean([r[f"cont_{w}"] for r in v]), np.mean([r[f"ctrl_cont_{w}"] for r in v])) for v in by.values()]
        res[f"continuation {w} (bp)"] = {"event_mean_by_session": round(1e4 * float(np.mean([a for a, _b in ses])), 1),
                                          "control_mean_by_session": round(1e4 * float(np.mean([b for _a, b in ses])), 1),
                                          "sessions_event_above_control": int(sum(a > b for a, b in ses)),
                                          "issuer_event_mean": round(1e4 * float(np.mean([r[f"cont_{w}"] for r in ok])), 1),
                                          "issuer_share_continuing": round(float(np.mean([r[f"cont_{w}"] > 0 for r in ok])), 3)}
    res["mean_abs_abnR1_bp"] = {"event": round(1e4 * float(np.mean([abs(r["abn"]["R1"]) for r in ok])), 1),
                                "matched_control": round(1e4 * float(np.mean([r["ctrl_mean_absR1"] for r in ok])), 1)}
    # NIFTY mapping and pricing
    import op  # noqa: E402  (gl's cached sessions; read only)
    smp, _days, _au = op.setup()
    nm = []
    for d, v in sorted(by.items()):
        sig = sum(W[r["symbol"]] * r["abn"]["R1"] for r in v)
        side = "CE" if sig > 0 else "PE"
        wi = windows(ib[d], prev_close(idd, d))
        row = {"day": d, "signal_bp": round(1e4 * sig, 2), "side": side, "nifty_R2a_bp": round(1e4 * wi["R2a"], 1) if wi else None}
        row["hit"] = None if wi is None else bool(np.sign(wi["R2a"]) == np.sign(sig))
        s = smp.s.get(d)
        for st in (205.0, 400.0):
            if s is None or s["day"] == s["expiry"]:
                row[f"net@{int(st)}"] = None
                row["price_state"] = "NO_SESSION" if s is None else "EXPIRY_DAY"
                continue
            pos, dep, state, jf = op.leg(smp, s, side, 30, "HONEST", st, depths=(1,))
            row["price_state"] = state
            if pos is None:
                row[f"net@{int(st)}"] = None
                continue
            v_, why = op.net_from_path(op.path(pos, s, jf, jf + 120), 120)
            row[f"net@{int(st)}"] = None if v_ is None else round(v_, 1)
            row["exit"] = why
        nm.append(row)
    res["nifty_mapping"] = nm
    hits = [r["hit"] for r in nm if r["hit"] is not None]
    res["nifty_hit_rate"] = round(float(np.mean(hits)), 3) if hits else None
    for st in (205, 400):
        xs = [r[f"net@{st}"] for r in nm if r.get(f"net@{st}") is not None]
        res[f"nifty_priced@{st}"] = {"n": len(xs), "mean": round(float(np.mean(xs))) if xs else None, "sum": round(sum(xs)) if xs else None}
    res["verdict"] = "INSUFFICIENT" if len(by) < 20 else "SCREENED"
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=float))


if __name__ == "__main__":
    main()
