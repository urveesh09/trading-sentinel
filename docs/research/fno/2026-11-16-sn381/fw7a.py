"""SN381: the companion audit for SN380 (fw7) and SN353 (c) (fw5), frozen before any forward P&L is seen (PLAN.md
section 1). fw5 / fw7 stay as frozen and their verdicts are still produced; this file adds the corrected rules.

Corrections (the auditor's three flaws, verified in the code):
  CASH     a leg is admissible only if the one-lot WALKED ask (5 levels) plus entry charges <= Rs 15,000 (wallet - Rs
           15,000 at a Rs 30,000 wallet); depth 2 is tried first, then depth 1; neither -> INADMISSIBLE. The buy order's
           limit is min(ask at the decision + 2 ticks, the price at which one lot plus charges is exactly the room), so
           no fill can exceed the room; a walked fill above it is MISSED (capped).
  TIMING   the auction price comes from a packet RECEIVED before the 09:16:00 decision: MATCH (the pre-open match
           packet, 09:08:00 - 09:15:00, last-trade time on this day) or FIRST_TRADE (the first continuous packet,
           received at or after 09:15:00 and no later than 09:16:00); otherwise NO_SIGNAL. The source is recorded.
  CONTROLS paired: the candidate and a control are compared only on sessions where BOTH filled (mean paired difference,
           date-level standard error, without the best day); and separately per eligible session with every
           INADMISSIBLE / NO_SIGNAL / MISSED decision scored 0 and UNRESOLVED disclosed (fw2 scores it as the premium
           lost).
Ledger states: INADMISSIBLE, NO_SIGNAL, MISSED, FILLED, UNRESOLVED; with signal source and receipt time, quote receipt,
cash before / after, fill / exit / stop times.
Verdict (once, SN300a's first 20 qualified non-expiry sessions, the same list as fw5 / fw7, written to the receipt):
PASS = per-session net > 0 at Rs 205 and Rs 400, paired lift > 0 against both controls (ATM; coin-flip at the same depth
and admissibility rules) with >= 10 common fills each, > 0 without the best day; fewer than 15 fills = INSUFFICIENT.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn351"))
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
ROOM = 15000.0
TICK = 0.05
TDEC, HOLD = 60.0, 3600.0
OUT = HERE / "results-sn381-fw7a.json"


def charges_buy(px, qty):
    import fw2
    return fw2.charges(px, 0.0, qty)


# ---- pure rules (tested in test_fw7a.py) ------------------------------------------------------------------------------
def walk_cost(prices, qtys, need):
    got, cost = 0.0, 0.0
    for p, q in zip(prices, qtys):
        if p <= 0 or q <= 0:
            continue
        take = min(q, need - got)
        cost += take * p
        got += take
        if got >= need:
            return cost / need
    return None


def admissible(prices, qtys, lot, charges_fn=None, room=ROOM):
    """(ok, walked price, cost incl. entry charges) for one lot at this book."""
    px = walk_cost(prices, qtys, lot)
    if px is None:
        return False, None, None
    cost = px * lot + (charges_fn(px, lot) if charges_fn else 0.0)
    return cost <= room + 1e-9, px, cost


def pick_depth(books, lot, charges_fn=None, room=ROOM):
    """books: {depth: (prices, qtys)} for depths 2 and 1; the deeper admissible one, else None (INADMISSIBLE)."""
    for depth in (2, 1):
        if depth in books:
            ok, px, cost = admissible(*books[depth], lot, charges_fn, room)
            if ok:
                return depth, px, cost
    return None, None, None


def order_cap(ask, lot, charges_fn=None, room=ROOM):
    """The buy limit: ask + 2 ticks, never above the price at which one lot plus charges fills the room."""
    hi = ask + 2 * TICK
    lo = 0.0
    if charges_fn is None:
        return min(hi, room / lot)
    for _ in range(40):                          # the largest price whose lot cost + charges <= room
        mid = 0.5 * (lo + hi)
        if mid * lot + charges_fn(mid, lot) <= room:
            lo = mid
        else:
            hi = mid
    return min(ask + 2 * TICK, lo)


def auction_price(rows, decision_t, pre0_epoch):
    """rows: list of dicts with t (s after 09:15, receipt), ltp, last_trade_ts (epoch). -> (price, source, receipt t)."""
    for r in rows:
        if -420.0 <= r["t"] < 0.0 and r.get("last_trade_ts", 0) >= pre0_epoch:
            return r["ltp"], "MATCH", r["t"]
    for r in rows:
        if r["t"] >= 0.0:
            if r["t"] <= decision_t:
                return r["ltp"], "FIRST_TRADE", r["t"]
            return None, "NO_SIGNAL", r["t"]
    return None, "NO_SIGNAL", None


def state_of(trade_row):
    if trade_row is None:
        return "INADMISSIBLE"
    if trade_row.get("missed"):
        return "MISSED"
    if trade_row.get("status") == "unresolved":
        return "UNRESOLVED"
    return "FILLED"


def judge(rows, arm="ITM", controls=("ATM", "COIN_ITM"), stresses=(205, 400)):
    """rows: one per eligible session: {"day", arm: {"state", "net205", "net400"}, control: {...}}."""
    out = {"sessions": len(rows)}
    filled = [r for r in rows if r[arm]["state"] in ("FILLED", "UNRESOLVED")]
    out["fills"] = len(filled)
    out["unresolved"] = sum(r[arm]["state"] == "UNRESOLVED" for r in rows)
    out["states"] = {s: sum(r[arm]["state"] == s for r in rows) for s in ("INADMISSIBLE", "NO_SIGNAL", "MISSED", "FILLED", "UNRESOLVED")}
    for st in stresses:
        per = [r[arm][f"net{st}"] if r[arm]["state"] in ("FILLED", "UNRESOLVED") else 0.0 for r in rows]
        out[f"per_session_{st}"] = round(float(np.mean(per)), 1) if per else None
        by_day = {r["day"]: v for r, v in zip(rows, per)}
        best = max(by_day.values()) if by_day else 0.0
        out[f"without_best_day_{st}"] = round(float(sum(per) - best), 1)
    paired = {}
    for c in controls:
        common = [r for r in rows if r[arm]["state"] in ("FILLED", "UNRESOLVED") and r[c]["state"] in ("FILLED", "UNRESOLVED")]
        d = np.array([r[arm]["net205"] - r[c]["net205"] for r in common]) if common else np.array([])
        paired[c] = {"common_fills": len(common), "mean_diff_205": round(float(d.mean()), 1) if len(d) else None,
                     "se_by_date": round(float(d.std(ddof=1) / np.sqrt(len(d))), 1) if len(d) > 1 else None}
    out["paired"] = paired
    if out["fills"] < 15:
        out["verdict"] = "INSUFFICIENT"
    else:
        ok = (out["per_session_205"] > 0 and out["per_session_400"] > 0 and out["without_best_day_205"] > 0
              and all(p["common_fills"] >= 10 and (p["mean_diff_205"] or -1) > 0 for p in paired.values()))
        out["verdict"] = "PASS" if ok else "FAIL"
    return out


# ---- the recorder session (fw2 / fw5 machinery) ----------------------------------------------------------------------
def session(folder):
    import datetime as dt
    import fw2
    import fw5
    day = fw2.Day(folder, fw5.load_open(folder))
    out = {"day": day.day}
    if day.expiry_day:
        out["skip"] = "expiry_day"
        return out
    f = day.D.get(day.fut)
    if f is None or "buy_qty" not in f:
        out["skip"] = "no_future"
        return out
    pre0 = fw5.IST.localize(dt.datetime.fromisoformat(day.day + "T09:00:00")).timestamp()
    rows = [{"t": float(f["t"][k]), "ltp": float(f["ltp"][k]), "last_trade_ts": float(f["last_trade_ts"][k])} for k in range(len(f["t"])) if f["t"][k] >= -900]
    k6 = fw5.last_at(f, fw5.T06)
    C0 = float(f["close"][k6]) if k6 is not None else None
    A, source, at = auction_price(rows, TDEC, pre0)
    k5 = fw5.last_at(f, fw5.T05)
    out.update(source=source, signal_receipt_t=at, A=A, C0=C0,
               iep_0905=None if k5 is None else float(f["open"][k5]), iep_0906=None if k6 is None else float(f["open"][k6]))
    if A is None or not C0:
        for arm in ("ITM", "ATM", "COIN_ITM"):
            out[arm] = {"state": "NO_SIGNAL", "net205": 0.0, "net400": 0.0}
        return out
    g = A / C0 - 1.0
    out["g"] = g
    atm = day.atm(TDEC)
    lot = day.lot
    cfn = lambda px, q: charges_buy(px, q)  # noqa: E731

    def book_at(tok):
        d = day.D.get(tok)
        if d is None or "asks" not in d:
            return None
        k = int(np.searchsorted(d["t"], TDEC, side="right")) - 1
        while k >= 0 and not d["ok"][k]:
            k -= 1
        if k < 0:
            return None
        return (list(d["asks"][:, k]), list(d["askq"][:, k]), float(d["ask"][k]), float(d["t"][k]))

    def leg(side, depths=(2, 1)):
        sgn = -1 if side == "CE" else 1
        books, toks = {}, {}
        for dep in depths:
            tok = day.opt.get((day.front, atm + sgn * dep * 50, side)) if dep else day.opt.get((day.front, atm, side))
            b = None if tok is None else book_at(tok)
            if b is not None:
                books[dep], toks[dep] = (b[0], b[1]), (tok, b[2], b[3])
        dep, px, cost = pick_depth(books, lot, cfn) if depths != (0,) else (
            (0, *admissible(*books[0], lot, cfn)[1:]) if 0 in books and admissible(*books[0], lot, cfn)[0] else (None, None, None))
        if dep is None:
            return {"state": "INADMISSIBLE", "net205": 0.0, "net400": 0.0}
        tok, ask, qt = toks[dep]
        cap = order_cap(ask, lot, cfn)
        r = fw2.trade(day, tok, TDEC, HOLD, cap=cap)
        r.update(depth=dep, decision_cost=round(cost, 2), cap=round(cap, 2), quote_receipt_t=qt, cash_before=30000.0)
        st = state_of(r)
        r["state"] = st
        if st in ("FILLED", "UNRESOLVED"):
            r["cash_after_entry"] = round(30000.0 - r["debit"], 2)
            assert r["debit"] <= ROOM + 1e-6, ("room breached", r["debit"])
        else:
            r["net205"] = r["net400"] = 0.0
        return r
    side = "CE" if g > 0 else "PE"
    coin = random.Random(f"sn381-{day.day}").choice(("CE", "PE"))
    out["ITM"] = leg(side)
    out["ATM"] = leg(side, depths=(0,))
    out["COIN_ITM"] = leg(coin)
    out["coin_side"] = coin
    return out


def verdict():
    import fw5
    if OUT.exists():
        raise SystemExit("fw7a is scored once")
    days = sorted(p.name for p in fw5.ARCH.iterdir() if p.is_dir() and p.name >= fw5.START) if fw5.ARCH.exists() else []
    rows, skipped = [], []
    for d in days:
        rc = fw5.REC / f"{d}.json"
        q = json.loads(rc.read_text(encoding="utf-8")).get("qualify", {}) if rc.exists() else {}
        if not q.get("ok"):
            skipped.append({"day": d, "why": "not qualified"})
            continue
        r = session(fw5.ARCH / d)
        if r.get("skip"):
            skipped.append({"day": d, "why": r["skip"]})
            continue
        rows.append(r)
        if len(rows) == fw5.N_SESSIONS:
            break
    if len(rows) < fw5.N_SESSIONS:
        raise SystemExit(f"{len(rows)} of {fw5.N_SESSIONS} sessions so far; the verdict waits")
    res = {"session_list": [r["day"] for r in rows], "skipped": skipped, "ITM": judge(rows),
           "by_source": {s: judge([r for r in rows if r.get("source") == s]) for s in ("MATCH", "FIRST_TRADE")}, "rows": rows}
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "dev":
        r = session(Path(sys.argv[2]))
        print(json.dumps({k: (v if not isinstance(v, dict) else {x: v.get(x) for x in ("state", "depth", "decision_cost", "cap", "latency", "status")})
                          for k, v in r.items() if k not in ("A", "C0", "g", "iep_0905", "iep_0906")}, default=float))
    elif len(sys.argv) > 1 and sys.argv[1] == "verdict":
        verdict()
    else:
        raise SystemExit("usage: fw7a.py dev FOLDER | verdict")
