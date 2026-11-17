"""SN396 C: the audit companion of fw7a (frozen Nov 17, 2026, before any forward P&L is seen; PLAN.md section 1 at
00693405). fw7a stays as frozen and its verdict is still produced; this file is published beside it.

What changes from fw7a (everything else is fw7a's rule, line for line):
  LEGAL FILL   the buy limit is fw7a's cap; only ask levels at or below it count. The full lot must be available at or
               below the cap in ONE packet inside fw2's entry window (0.5 - 2.5 s after the decision); the price is the
               walk over those levels. A packet holding part of a lot at or below the cap is counted PENDING_PARTIAL
               and the order keeps waiting; if no packet holds a full lot, the decision is MISSED (reason kept). A
               one-lot order never partially executes here: a full-lot execution is required, as fw7a assumed.
  ZERO GAP     an auction price exactly equal to the previous close (g == 0) is NO_SIGNAL (fw7a sent it to PE).
  PER STRESS   the hold and its exit status are recorded for each stress; an exit unresolved at one stress is booked
               as the premium lost at that stress (fw2's net_of) and disclosed per stress.
Verdict (once, the same 20 sessions as fw7a): fw7a.judge on fw7b's rows, published with fw7a's.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn381"))
sys.path.insert(0, str(FNO / "2026-11-16-sn351"))
sys.path.insert(0, str(FNO / "2026-11-16-sn301"))
import fw7a  # noqa: E402

OUT = HERE / "results-sn396-fw7b.json"
ROOM, TDEC, HOLD = fw7a.ROOM, fw7a.TDEC, fw7a.HOLD


# ---- pure rules (tested in test_fw9a.py) ------------------------------------------------------------------------------
def legal_walk(prices, qtys, need, cap):
    """Walk only levels priced at or below cap. -> (price, got): price None unless the full lot is available."""
    got, cost = 0.0, 0.0
    for p, q in zip(prices, qtys):
        if p <= 0 or q <= 0 or p > cap + 1e-9:
            continue
        take = min(q, need - got)
        cost += take * p
        got += take
        if got >= need:
            return cost / need, got
    return None, got


def side_of(g):
    if g is None or g == 0:
        return None
    return "CE" if g > 0 else "PE"


def entry_legal(day, tok, td, cap, lat0=0.5, width=2.0):
    """((k, price), 'filled', partials) or (None, reason, partials)."""
    d = day.D.get(tok)
    if d is None or "ok" not in d:
        return None, "no_instrument", 0
    k = int(np.searchsorted(d["t"], td + lat0, side="left"))
    why, partials = "no_packet", 0
    while k < len(d["t"]) and d["t"][k] <= td + lat0 + width:
        if not d["ok"][k]:
            why = "invalid_or_stale"
        else:
            px, got = legal_walk(d["asks"][:, k], d["askq"][:, k], day.lot, cap)
            if px is not None:
                return (k, px), "filled", partials
            if got > 0:
                partials += 1
                why = "partial_only"
            elif why != "partial_only":
                why = "capped_or_no_depth"
        k += 1
    return None, why, partials


def trade_legal(day, tok, td, hold_s, cap):
    import fw2
    got, why, partials = entry_legal(day, tok, td, cap)
    if got is None:
        return {"missed": True, "why": why, "pending_partial_packets": partials}
    k, px = got
    d = day.D[tok]
    tf = float(d["t"][k])
    row = {"missed": False, "fill_t": round(tf, 3), "latency": round(tf - td, 3), "px_in": px, "pending_partial_packets": partials,
           "debit": round(px * day.lot + fw2.charges(px, 0.0, day.lot), 2), "premium": round(px * day.lot, 2), "status_by_stress": {}}
    for s in fw2.STRESSES:
        h = fw2.hold(day, tok, k, px, tf + hold_s, s)
        row[f"net{int(s)}"] = h["net"]
        row["status_by_stress"][str(int(s))] = h["status"]
        if s == fw2.STRESSES[0]:
            row.update(tx=round(h["tx"], 3), why=h["why"], status=h["status"])
    row["unresolved_any"] = any(v == "unresolved" for v in row["status_by_stress"].values())
    return row


def state_of(r):
    if r is None:
        return "INADMISSIBLE"
    if r.get("missed"):
        return "MISSED"
    if r.get("unresolved_any"):
        return "UNRESOLVED"
    return "FILLED"


# ---- the recorder session ----------------------------------------------------------------------------------------------
def session(folder):
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
    A, source, at = fw7a.auction_price(rows, TDEC, pre0)
    out.update(source=source, signal_receipt_t=at, A=A, C0=C0)
    g = None if (A is None or not C0) else A / C0 - 1.0
    side = side_of(g)
    out["g"] = g
    if side is None:
        out["zero_gap"] = g == 0
        for arm in ("ITM", "ATM", "COIN_ITM"):
            out[arm] = {"state": "NO_SIGNAL", "net205": 0.0, "net400": 0.0}
        return out
    atm = day.atm(TDEC)
    lot = day.lot
    cfn = fw7a.charges_buy

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

    def leg(sd, depths=(2, 1)):
        sgn = -1 if sd == "CE" else 1
        books, toks = {}, {}
        for dep in depths:
            tok = day.opt.get((day.front, atm + sgn * dep * 50, sd)) if dep else day.opt.get((day.front, atm, sd))
            b = None if tok is None else book_at(tok)
            if b is not None:
                books[dep], toks[dep] = (b[0], b[1]), (tok, b[2], b[3])
        if depths == (0,):
            ok = 0 in books and fw7a.admissible(*books[0], lot, cfn)[0]
            dep, px, cost = (0, *fw7a.admissible(*books[0], lot, cfn)[1:]) if ok else (None, None, None)
        else:
            dep, px, cost = fw7a.pick_depth(books, lot, cfn)
        if dep is None:
            return {"state": "INADMISSIBLE", "net205": 0.0, "net400": 0.0}
        tok, ask, qt = toks[dep]
        cap = fw7a.order_cap(ask, lot, cfn)
        r = trade_legal(day, tok, TDEC, HOLD, cap)
        r.update(depth=dep, decision_cost=round(cost, 2), cap=round(cap, 2), quote_receipt_t=qt, cash_before=30000.0)
        st = state_of(r)
        r["state"] = st
        if st in ("FILLED", "UNRESOLVED"):
            r["cash_after_entry"] = round(30000.0 - r["debit"], 2)
            assert r["debit"] <= ROOM + 1e-6, ("room breached", r["debit"])
        else:
            r["net205"] = r["net400"] = 0.0
        return r
    coin = random.Random(f"sn381-{day.day}").choice(("CE", "PE"))
    out["ITM"] = leg(side)
    out["ATM"] = leg(side, depths=(0,))
    out["COIN_ITM"] = leg(coin)
    out["coin_side"] = coin
    return out


def verdict():
    import fw5
    if OUT.exists():
        raise SystemExit("fw7b is scored once")
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
    res = {"session_list": [r["day"] for r in rows], "skipped": skipped, "ITM": fw7a.judge(rows),
           "by_source": {s: fw7a.judge([r for r in rows if r.get("source") == s]) for s in ("MATCH", "FIRST_TRADE")},
           "pending_partial_sessions": sum(1 for r in rows if (r.get("ITM") or {}).get("pending_partial_packets")),
           "unresolved_by_stress": {st: sum(1 for r in rows if ((r.get("ITM") or {}).get("status_by_stress") or {}).get(st) == "unresolved") for st in ("205", "400")},
           "zero_gap_sessions": sum(1 for r in rows if r.get("zero_gap")), "rows": rows}
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "dev":
        r = session(Path(sys.argv[2]))
        print(json.dumps({k: (v if not isinstance(v, dict) else {x: v.get(x) for x in ("state", "depth", "cap", "latency", "status_by_stress", "pending_partial_packets", "why")})
                          for k, v in r.items() if k not in ("A", "C0", "g")}, default=float))
    elif len(sys.argv) > 1 and sys.argv[1] == "verdict":
        verdict()
    else:
        raise SystemExit("usage: fw7b.py dev FOLDER | verdict")
